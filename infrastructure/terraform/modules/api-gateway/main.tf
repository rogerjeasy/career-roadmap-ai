terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.100"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.2"
    }
  }
}

# ─────────────────────────────────────────────────────────────────────────────
# Kong API Gateway — Azure Container Apps module
#
# Resources created:
#   1. kong-migrations-<env>   Container App Job  — bootstraps / migrates the
#                               Kong PostgreSQL schema before proxy starts
#   2. kong-gateway-<env>       Container App      — Kong proxy (external ingress
#                               on :8000; Azure terminates TLS at :443)
#
# The migrations job uses a null_resource to trigger itself automatically on
# every plan/apply cycle that changes DB connection variables. Kong itself
# depends on the trigger completing, so fresh deployments are always safe.
# ─────────────────────────────────────────────────────────────────────────────

locals {
  # Shared DB environment variables — used in both the migration job and the proxy
  kong_db_env = [
    { name = "KONG_DATABASE",    value = "postgres" },
    { name = "KONG_PG_HOST",     value = var.postgres_host },
    { name = "KONG_PG_PORT",     value = tostring(var.postgres_port) },
    { name = "KONG_PG_USER",     value = var.postgres_user },
    { name = "KONG_PG_DATABASE", value = var.postgres_db_name },
    { name = "KONG_PG_SSL",      value = "on" },
    { name = "KONG_PG_SSL_VERIFY", value = "off" },
    # Password is injected from Container App secrets (not plaintext env)
    { name = "KONG_PG_PASSWORD", secret_name = "kong-pg-password" },
  ]

  # Full environment for the Kong proxy container
  kong_proxy_env = concat(local.kong_db_env, [
    # ── Listeners ─────────────────────────────────────────────
    # Azure Container Apps terminates TLS at the ingress layer, so Kong only
    # needs to listen on plain HTTP internally. The admin API is bound to
    # loopback — never reachable from the public internet.
    { name = "KONG_PROXY_LISTEN",  value = "0.0.0.0:8000" },
    { name = "KONG_ADMIN_LISTEN",  value = "127.0.0.1:8001" },
    # Status API used for Container App liveness/readiness probes.
    { name = "KONG_STATUS_LISTEN", value = "0.0.0.0:8100" },

    # ── Logging ───────────────────────────────────────────────
    { name = "KONG_PROXY_ACCESS_LOG",  value = "/dev/stdout" },
    { name = "KONG_ADMIN_ACCESS_LOG",  value = "/dev/stdout" },
    { name = "KONG_PROXY_ERROR_LOG",   value = "/dev/stderr" },
    { name = "KONG_ADMIN_ERROR_LOG",   value = "/dev/stderr" },
    { name = "KONG_LOG_LEVEL",         value = "notice" },

    # ── Performance ───────────────────────────────────────────
    { name = "KONG_NGINX_WORKER_PROCESSES",       value = "auto" },
    # Disable Nginx response buffering so SSE streams are flushed immediately.
    { name = "KONG_NGINX_PROXY_PROXY_BUFFERING",  value = "off" },

    # ── Plugins ───────────────────────────────────────────────
    { name = "KONG_PLUGINS", value = "bundled" },

    # ── Distributed tracing ───────────────────────────────────
    # The opentelemetry plugin reads these to attach resource attributes.
    { name = "KONG_TRACING_INSTRUMENTATIONS", value = "all" },
    { name = "KONG_TRACING_SAMPLING_RATE",    value = "1.0" },

    # ── Cluster ───────────────────────────────────────────────
    # All Kong replicas share state via PostgreSQL; no extra cluster config needed.
    { name = "KONG_CLUSTER_CONTROL_PLANE", value = "" },
  ])
}

# ─── 1. Migrations Job ────────────────────────────────────────────────────────

resource "azurerm_container_app_job" "kong_migrations" {
  name                         = "kong-migrations-${var.environment}"
  location                     = var.location
  resource_group_name          = var.resource_group_name
  container_app_environment_id = var.container_app_environment_id

  replica_timeout_in_seconds = 300
  replica_retry_limit        = 2

  # Manual trigger — the null_resource below fires it on deploy.
  manual_trigger_config {
    parallelism              = 1
    replica_completion_count = 1
  }

  template {
    container {
      name   = "kong-migrations"
      image  = "kong:${var.kong_version}"
      cpu    = var.migration_cpu
      memory = var.migration_memory

      # Run 'kong migrations up' to apply pending schema changes idempotently.
      # 'bootstrap' is only needed on a brand-new database; 'up' handles both.
      command = ["/bin/sh", "-c", "kong migrations bootstrap 2>/dev/null; kong migrations up"]

      dynamic "env" {
        for_each = local.kong_db_env
        content {
          name        = env.value.name
          secret_name = lookup(env.value, "secret_name", null)
          value       = lookup(env.value, "value", null)
        }
      }
    }
  }

  secret {
    name  = "kong-pg-password"
    value = var.postgres_password
  }

  tags = var.tags
}

# ─── 2. Trigger migrations on every DB-related change ─────────────────────────

resource "null_resource" "run_kong_migrations" {
  # Trigger a new migration run whenever the DB connection config changes.
  triggers = {
    pg_host     = var.postgres_host
    pg_port     = var.postgres_port
    pg_user     = var.postgres_user
    pg_db       = var.postgres_db_name
    kong_ver    = var.kong_version
    job_name    = azurerm_container_app_job.kong_migrations.name
    rg_name     = var.resource_group_name
  }

  provisioner "local-exec" {
    command = <<-EOT
      az containerapp job start \
        --name "${azurerm_container_app_job.kong_migrations.name}" \
        --resource-group "${var.resource_group_name}" \
        --output none
      echo "Kong migrations job triggered. Waiting for completion..."
      # Poll until the job execution succeeds (max 5 minutes)
      for i in $(seq 1 30); do
        STATUS=$(az containerapp job execution list \
          --name "${azurerm_container_app_job.kong_migrations.name}" \
          --resource-group "${var.resource_group_name}" \
          --query "[0].properties.status" -o tsv 2>/dev/null)
        echo "Migration status: $STATUS"
        if [ "$STATUS" = "Succeeded" ]; then
          echo "Migrations completed successfully."
          exit 0
        elif [ "$STATUS" = "Failed" ]; then
          echo "ERROR: Kong migrations job failed." >&2
          exit 1
        fi
        sleep 10
      done
      echo "ERROR: Timed out waiting for Kong migrations." >&2
      exit 1
    EOT
    interpreter = ["/bin/sh", "-c"]
  }

  depends_on = [azurerm_container_app_job.kong_migrations]
}

# ─── 3. Kong Proxy Container App ──────────────────────────────────────────────

resource "azurerm_container_app" "kong" {
  name                         = "kong-gateway-${var.environment}"
  location                     = var.location
  resource_group_name          = var.resource_group_name
  container_app_environment_id = var.container_app_environment_id
  revision_mode                = "Single"

  # External ingress: Azure handles TLS on :443 → forwards plain HTTP to Kong :8000
  ingress {
    external_enabled = true
    target_port      = 8000
    allow_insecure_connections = false

    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  template {
    min_replicas = var.min_replicas
    max_replicas = var.max_replicas

    container {
      name   = "kong"
      image  = "kong:${var.kong_version}"
      cpu    = var.cpu
      memory = var.memory

      dynamic "env" {
        for_each = local.kong_proxy_env
        content {
          name        = env.value.name
          secret_name = lookup(env.value, "secret_name", null)
          value       = lookup(env.value, "value", null)
        }
      }

      # Status API liveness probe: Kong is healthy when it can serve /status
      liveness_probe {
        path                    = "/status"
        port                    = 8100
        transport               = "HTTP"
        initial_delay           = 20
        period_seconds          = 15
        timeout_seconds         = 5
        failure_count_threshold = 3
        success_count_threshold = 1
      }

      # Status API readiness probe: Kong is ready when DB + plugins are loaded
      readiness_probe {
        path                    = "/status/ready"
        port                    = 8100
        transport               = "HTTP"
        initial_delay           = 10
        period_seconds          = 10
        timeout_seconds         = 5
        failure_count_threshold = 3
        success_count_threshold = 1
      }
    }

    # Scale out when concurrent HTTP requests exceed 100 per replica.
    http_scale_rule {
      name                = "http-traffic"
      concurrent_requests = "100"
    }
  }

  secret {
    name  = "kong-pg-password"
    value = var.postgres_password
  }

  tags = var.tags

  # Ensure migrations have run before Kong starts on first deploy.
  depends_on = [null_resource.run_kong_migrations]
}

# ─────────────────────────────────────────────────────────────────────────────
# Post-deploy: push declarative config via deck
#
# After Terraform provisions Kong, run in CI/CD:
#
#   deck sync \
#     --state infrastructure/kong/kong.yml \
#     --env-file infrastructure/kong/.env.production \
#     --kong-addr "https://$(terraform output -raw kong_proxy_fqdn)"
#
# deck communicates through the Kong Admin API (port 8001). In production the
# Admin API is bound to loopback (127.0.0.1). Access it via:
#   az containerapp exec --name kong-gateway-production ... \
#     --command "curl http://localhost:8001"
# Or expose it temporarily via a Container App revision with a restricted
# IP-allow list, then roll back.
# ─────────────────────────────────────────────────────────────────────────────
