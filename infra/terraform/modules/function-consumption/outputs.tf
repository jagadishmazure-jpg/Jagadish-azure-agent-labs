output "name" {
  value = azurerm_linux_function_app.this.name
}

output "hostname" {
  value = azurerm_linux_function_app.this.default_hostname
}
