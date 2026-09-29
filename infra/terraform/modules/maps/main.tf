# Azure Maps (Gen2) with shared-key auth disabled; callers use Entra ID.
resource "azurerm_maps_account" "this" {
  name                         = var.name
  resource_group_name          = var.resource_group_name
  location                     = "global"
  tags                         = var.tags
  sku_name                     = "G2"
  local_authentication_enabled = false
}

resource "azurerm_role_assignment" "reader" {
  for_each                         = var.reader_principal_ids
  scope                            = azurerm_maps_account.this.id
  role_definition_name             = "Azure Maps Data Reader"
  principal_id                     = each.value
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}
