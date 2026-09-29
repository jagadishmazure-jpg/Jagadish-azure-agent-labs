output "id" {
  value = azurerm_eventhub_namespace.this.id
}

output "fqdn" {
  value = "${azurerm_eventhub_namespace.this.name}.servicebus.windows.net"
}
