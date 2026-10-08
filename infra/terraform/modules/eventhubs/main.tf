# Event Hubs namespace (Standard, keyless) with hubs and optional consumer groups.
resource "azurerm_eventhub_namespace" "this" {
  name                          = var.name
  resource_group_name           = var.resource_group_name
  location                      = var.location
  tags                          = var.tags
  sku                           = "Standard"
  capacity                      = 1
  local_authentication_enabled  = false
  minimum_tls_version           = "1.2"
  public_network_access_enabled = var.public_network_access_enabled
}

resource "azurerm_eventhub" "this" {
  for_each          = var.hubs
  name              = each.key
  namespace_id      = azurerm_eventhub_namespace.this.id
  partition_count   = each.value.partitions
  message_retention = each.value.retention_days
}

resource "azurerm_eventhub_consumer_group" "this" {
  for_each            = var.consumer_groups
  name                = each.key
  namespace_name      = azurerm_eventhub_namespace.this.name
  eventhub_name       = azurerm_eventhub.this[each.value].name
  resource_group_name = var.resource_group_name
}

resource "azurerm_role_assignment" "receiver" {
  for_each                         = var.receiver_principal_ids
  scope                            = azurerm_eventhub_namespace.this.id
  role_definition_name             = "Azure Event Hubs Data Receiver"
  principal_id                     = each.value
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

# Optional private endpoint (namespace sub-resource) with its DNS zone group; Standard tier supports it.
resource "azurerm_private_endpoint" "this" {
  count               = var.private_endpoint == null ? 0 : 1
  name                = "pe-${var.name}"
  resource_group_name = var.resource_group_name
  location            = var.location
  tags                = var.tags
  subnet_id           = var.private_endpoint.subnet_id

  private_service_connection {
    name                           = "pe-${var.name}"
    private_connection_resource_id = azurerm_eventhub_namespace.this.id
    subresource_names              = ["namespace"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "default"
    private_dns_zone_ids = [var.private_endpoint.dns_zone_id]
  }
}
