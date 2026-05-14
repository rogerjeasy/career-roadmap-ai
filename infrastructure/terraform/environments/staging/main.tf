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

  backend "azurerm" {
    resource_group_name  = "career-roadmap-tfstate"
    storage_account_name = "craiterraformstate"
    container_name       = "tfstate"
    key                  = "staging.terraform.tfstate"
  }
}

provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
}

# ─── Resource Group ───────────────────────────────────────────────────────────

resource "azurerm_resource_group" "main" {
  name     = "career-roadmap-staging"
  location = var.location
  tags     = local.tags
}

# ─── Container Apps Environment ───────────────────────────────────────────────

resource "azurerm_log_analytics_workspace" "main" {
  name                = "crai-logs-staging"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 7
  tags                = local.tags
}

resource "azurerm_container_app_environment" "main" {
  name                       = "crai-env-staging"
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  tags                       = local.tags
}

# ─── Kong API Gateway ─────────────────────────────────────────────────────────

module "api_gateway" {
  source = "../../modules/api-gateway"

  environment                  = "staging"
  location                     = azurerm_resource_group.main.location
  resource_group_name          = azurerm_resource_group.main.name
  container_app_environment_id = azurerm_container_app_environment.main.id

  kong_version = "3.8"

  postgres_host     = var.postgres_host
  postgres_user     = var.kong_postgres_user
  postgres_password = var.kong_postgres_password
  postgres_db_name  = "kong_staging"

  redis_host     = var.redis_host
  redis_port     = 6380
  redis_password = var.redis_password

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

  cors_origin_frontend = "https://${var.frontend_domain}"
  otel_endpoint_host   = var.otel_endpoint_host

  # Staging runs lean — single replica, smaller containers
  min_replicas = 1
  max_replicas = 2
  cpu          = 0.25
  memory       = "0.5Gi"

  tags = local.tags
}

# ─── Locals ───────────────────────────────────────────────────────────────────

locals {
  tags = {
    environment = "staging"
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
  description = "Azure region"
  type        = string
  default     = "West Europe"
}

variable "postgres_host" {
  type = string
}

variable "kong_postgres_user" {
  type    = string
  default = "kong"
}

variable "kong_postgres_password" {
  type      = string
  sensitive = true
}

variable "redis_host" {
  type = string
}

variable "redis_password" {
  type      = string
  sensitive = true
}

variable "frontend_domain" {
  description = "Staging frontend domain (e.g. staging.career-roadmap.example.com)"
  type        = string
}

variable "otel_endpoint_host" {
  type    = string
  default = ""
}

# ─── Outputs ──────────────────────────────────────────────────────────────────

output "kong_proxy_url" {
  description = "Kong proxy public URL — set as NEXT_PUBLIC_API_URL in the staging frontend"
  value       = module.api_gateway.kong_proxy_url
}

output "kong_proxy_fqdn" {
  value = module.api_gateway.kong_proxy_fqdn
}
