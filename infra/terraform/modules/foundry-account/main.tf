# Foundry (AIServices) account using the lab's user-assigned identity, keyless, with one model
# deployment. DataZoneStandard keeps inference processing inside the chosen data zone (us/eu).
resource "azurerm_cognitive_account" "this" {
  name                          = var.name
  resource_group_name           = var.resource_group_name
  location                      = var.location
  tags                          = var.tags
  kind                          = "AIServices"
  sku_name                      = "S0"
  custom_subdomain_name         = var.name
  local_auth_enabled            = false
  public_network_access_enabled = true

  identity {
    type         = "UserAssigned"
    identity_ids = [var.identity_id]
  }

  network_acls {
    default_action = "Allow"
  }
}

resource "azurerm_cognitive_deployment" "this" {
  name                 = var.deployment_name
  cognitive_account_id = azurerm_cognitive_account.this.id

  model {
    format  = "OpenAI"
    name    = var.model_name
    version = var.model_version
  }

  sku {
    name     = var.deployment_sku
    capacity = var.capacity
  }
}

resource "azurerm_role_assignment" "openai_user" {
  scope                            = azurerm_cognitive_account.this.id
  role_definition_name             = "Cognitive Services OpenAI User"
  principal_id                     = var.identity_principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}
