output "AZURE_RESOURCE_GROUP" {
  value = azurerm_resource_group.this.name
}

output "dataZone" {
  value = var.data_zone
}

output "identityClientId" {
  value = module.foundation.identity_client_id
}

output "foundryEndpoint" {
  value = module.foundry.endpoint
}

output "keyVaultUri" {
  value = module.foundation.key_vault_uri
}

output "docIntelEndpoint" {
  value = module.docintel.endpoint
}
