terraform {
  required_version = ">=1.7"
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

  # Store Terraform state in Azure Blob Storage.
  # Create the storage account + container before the first init.
  backend "azurerm" {
    resource_group_name  = "career-roadmap-tfstate"
    storage_account_name = "craiterraformstate"
    container_name       = "tfstate"
    key                  = "production.terraform.tfstate"
  }
}

provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
}

# ─── Resource Group ───────────────────────────────────────────────────────────

resource "azurerm_resource_group" "main" {
  name     = "career-roadmap-production"
  location = var.location
  tags     = local.tags
}

# ─── Container Apps Environment ───────────────────────────────────────────────
# Shared environment for Kong, FastAPI, Celery workers, and all MCP servers.

resource "azurerm_log_analytics_workspace" "main" {
  name                = "crai-logs-production"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.tags
}

resource "azurerm_container_app_environment" "main" {
  name                       = "crai-env-production"
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  tags                       = local.tags
}

# ─── Kong API Gateway ─────────────────────────────────────────────────────────

module "api_gateway" {
  source = "../../modules/api-gateway"

  environment                  = "production"
  location                     = azurerm_resource_group.main.location
  resource_group_name          = azurerm_resource_group.main.name
  container_app_environment_id = azurerm_container_app_environment.main.id

  kong_version = "3.8"

  # PostgreSQL — point at the Azure Database for PostgreSQL Flexible Server
  # created by the database module. Kong gets its own schema on the same server.
  postgres_host     = var.postgres_host
  postgres_user     = var.kong_postgres_user
  postgres_password = var.kong_postgres_password
  postgres_db_name  = "kong"

  # Redis — Azure Cache for Redis (TLS port 6380, database 9 reserved for Kong)
  redis_host     = var.redis_host
  redis_port     = 6380
  redis_password = var.redis_password

  # Upstream addresses — internal Container App DNS names within the environment
  fastapi_upstream_host = "fastapi-api"
  fastapi_upstream_port = 8000

  mcp_upstream_hosts = {
    job-board        = "mcp-job-board:3001"
    course-catalogue = "mcp-course-catalogue:3002"
    github-trends    = "mcp-github-trends:3003"
    salary-benchmark = "mcp-salary-benchmark:3004"
    social-signals   = "mcp-social-signals:3005"
    calendar         = "mcp-calendar:3006"
    industry-news    = "mcp-industry-news:3007"
  }

  # CORS — production frontend URL
  cors_origin_frontend = "https://${var.frontend_domain}"

  # Observability — OTel traces to Grafana Cloud / self-hosted Tempo
  otel_endpoint_host = var.otel_endpoint_host

  # Scaling: always keep at least 1 replica, scale up to 5 under load
  min_replicas = 1
  max_replicas = 5
  cpu          = 0.5
  memory       = "1Gi"

  tags = local.tags
}

# ─── Locals ───────────────────────────────────────────────────────────────────

locals {
  tags = {
    environment = "production"
    project     = "career-roadmap-ai"
    managed_by  = "terraform"
  }
}

# ─── Variables ────────────────────────────────────────────────────────────────

variable "subscription_id" {
  description = "Azure subscription ID"
  type        = string
}

variable "location" {
  description = "Azure region for all resources"
  type        = string
  default     = "West Europe"
}

variable "postgres_host" {
  description = "Azure Database for PostgreSQL Flexible Server FQDN"
  type        = string
}

variable "kong_postgres_user" {
  description = "PostgreSQL user for Kong schema"
  type        = string
  default     = "kong"
}

variable "kong_postgres_password" {
  description = "PostgreSQL password for the Kong user"
  type        = string
  sensitive   = true
}

variable "redis_host" {
  description = "Azure Cache for Redis FQDN"
  type        = string
}

variable "redis_password" {
  description = "Azure Cache for Redis primary access key"
  type        = string
  sensitive   = true
}

variable "frontend_domain" {
  description = "Production frontend domain (used for CORS, e.g. app.career-roadmap.example.com)"
  type        = string
}

variable "otel_endpoint_host" {
  description = "OTel collector / Tempo hostname for distributed tracing"
  type        = string
  default     = ""
}

# ─── Outputs ──────────────────────────────────────────────────────────────────

output "kong_proxy_url" {
  description = "Kong proxy public URL — set as NEXT_PUBLIC_API_URL in the frontend"
  value       = module.api_gateway.kong_proxy_url
}

output "kong_proxy_fqdn" {
  description = "Kong proxy FQDN (for DNS CNAME)"
  value       = module.api_gateway.kong_proxy_fqdn
}
