variable "environment" {
  description = "Deployment environment (staging | production)"
  type        = string
  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "environment must be 'staging' or 'production'."
  }
}

variable "location" {
  description = "Azure region"
  type        = string
}

variable "resource_group_name" {
  description = "Resource group that owns all created resources"
  type        = string
}

variable "container_app_environment_id" {
  description = "ID of the Azure Container Apps Environment shared by all services"
  type        = string
}

# ── Kong image ────────────────────────────────────────────────────────────────

variable "kong_version" {
  description = "Kong OSS Docker image tag"
  type        = string
  default     = "3.8"
}

# ── Database ──────────────────────────────────────────────────────────────────

variable "postgres_host" {
  description = "PostgreSQL server hostname (Azure Database for PostgreSQL Flexible Server FQDN)"
  type        = string
}

variable "postgres_port" {
  description = "PostgreSQL port"
  type        = number
  default     = 5432
}

variable "postgres_user" {
  description = "PostgreSQL admin user for Kong schema"
  type        = string
  default     = "kong"
}

variable "postgres_password" {
  description = "PostgreSQL password for the Kong user"
  type        = string
  sensitive   = true
}

variable "postgres_db_name" {
  description = "PostgreSQL database name for Kong"
  type        = string
  default     = "kong"
}

# ── Redis ─────────────────────────────────────────────────────────────────────
# Kong uses Redis exclusively for rate-limiting state (database 9).
# The same Redis instance used by FastAPI is fine; namespaced keys prevent conflicts.

variable "redis_host" {
  description = "Redis hostname (Azure Cache for Redis FQDN)"
  type        = string
}

variable "redis_port" {
  description = "Redis TLS port"
  type        = number
  default     = 6380
}

variable "redis_password" {
  description = "Redis access key"
  type        = string
  sensitive   = true
}

# ── Upstreams ─────────────────────────────────────────────────────────────────

variable "fastapi_upstream_host" {
  description = "Internal hostname or FQDN of the FastAPI Container App"
  type        = string
}

variable "fastapi_upstream_port" {
  description = "Port FastAPI listens on inside the Container App"
  type        = number
  default     = 8000
}

variable "mcp_upstream_hosts" {
  description = "Map from MCP service name to internal host:port. Keys must match names in kong.yml."
  type        = map(string)
  default = {
    job-board        = "mcp-job-board:3001"
    course-catalogue = "mcp-course-catalogue:3002"
    github-trends    = "mcp-github-trends:3003"
    salary-benchmark = "mcp-salary-benchmark:3004"
    social-signals   = "mcp-social-signals:3005"
    calendar         = "mcp-calendar:3006"
    industry-news    = "mcp-industry-news:3007"
  }
}

# ── CORS ──────────────────────────────────────────────────────────────────────

variable "cors_origin_frontend" {
  description = "Allowed CORS origin for the production frontend (e.g. https://app.example.com)"
  type        = string
}

# ── OTel ─────────────────────────────────────────────────────────────────────

variable "otel_endpoint_host" {
  description = "Hostname of the OTel collector / Grafana Tempo (without scheme or port)"
  type        = string
  default     = ""
}

# ── Scaling ───────────────────────────────────────────────────────────────────

variable "min_replicas" {
  description = "Minimum Kong proxy replicas"
  type        = number
  default     = 1
}

variable "max_replicas" {
  description = "Maximum Kong proxy replicas"
  type        = number
  default     = 3
}

variable "cpu" {
  description = "vCPUs per Kong Container App replica"
  type        = number
  default     = 0.5
}

variable "memory" {
  description = "Memory (GiB) per Kong Container App replica"
  type        = string
  default     = "1Gi"
}

variable "migration_cpu" {
  description = "vCPUs for the migrations job container"
  type        = number
  default     = 0.25
}

variable "migration_memory" {
  description = "Memory for the migrations job container"
  type        = string
  default     = "0.5Gi"
}

# ── Tagging ───────────────────────────────────────────────────────────────────

variable "tags" {
  description = "Azure resource tags applied to all created resources"
  type        = map(string)
  default     = {}
}
