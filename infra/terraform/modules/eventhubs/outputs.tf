output "id" {
  value = azurerm_eventhub_namespace.this.id
}

output "fqdn" {
  value = "${azurerm_eventhub_namespace.this.name}.servicebus.windows.net"
}

output "public_network_access_enabled" {
  value = azurerm_eventhub_namespace.this.public_network_access_enabled
}

output "private_endpoint_count" {
  value = length(azurerm_private_endpoint.this)
}
