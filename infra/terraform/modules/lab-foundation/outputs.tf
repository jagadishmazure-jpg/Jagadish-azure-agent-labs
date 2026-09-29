output "identity_id" {
  value = azurerm_user_assigned_identity.this.id
}

output "identity_principal_id" {
  value = azurerm_user_assigned_identity.this.principal_id
}

output "identity_client_id" {
  value = azurerm_user_assigned_identity.this.client_id
}

output "log_analytics_id" {
  value = azurerm_log_analytics_workspace.this.id
}

output "app_insights_connection_string" {
  value     = azurerm_application_insights.this.connection_string
  sensitive = true
}

output "key_vault_uri" {
  value = module.keyvault.uri
}

output "key_vault_name" {
  value = module.keyvault.name
}
