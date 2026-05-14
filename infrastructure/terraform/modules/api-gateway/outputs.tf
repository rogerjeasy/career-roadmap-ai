output "kong_proxy_url" {
  description = "Public HTTPS URL of the Kong proxy (frontend NEXT_PUBLIC_API_URL)"
  value       = "https://${azurerm_container_app.kong.ingress[0].fqdn}"
}

output "kong_proxy_fqdn" {
  description = "FQDN of the Kong proxy Container App (without scheme)"
  value       = azurerm_container_app.kong.ingress[0].fqdn
}

output "kong_container_app_name" {
  description = "Resource name of the Kong Container App (for deck --kong-addr lookup)"
  value       = azurerm_container_app.kong.name
}

output "kong_migrations_job_name" {
  description = "Resource name of the Kong migrations Container App Job"
  value       = azurerm_container_app_job.kong_migrations.name
}
