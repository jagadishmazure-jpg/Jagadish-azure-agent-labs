# Linux Function App on the Consumption (Y1) plan, running as the lab identity. The host storage
# connection is identity-based (AzureWebJobsStorage__credential = managedidentity).
resource "azurerm_service_plan" "this" {
  name                = var.plan_name
  resource_group_name = var.resource_group_name
  location            = var.location
  tags                = var.tags
  os_type             = "Linux"
  sku_name            = "Y1"
}

resource "azurerm_linux_function_app" "this" {
  name                          = var.name
  resource_group_name           = var.resource_group_name
  location                      = var.location
  tags                          = var.tags
  service_plan_id               = azurerm_service_plan.this.id
  https_only                    = true
  storage_account_name          = var.storage_account_name
  storage_uses_managed_identity = true
  public_network_access_enabled = true

  identity {
    type         = "UserAssigned"
    identity_ids = [var.identity_id]
  }

  key_vault_reference_identity_id = var.identity_id

  site_config {
    minimum_tls_version = "1.2"
    ftps_state          = "Disabled"
    http2_enabled       = true

    application_stack {
      python_version = "3.12"
    }
  }

  app_settings = merge({
    AzureWebJobsStorage__accountName          = var.storage_account_name
    AzureWebJobsStorage__credential           = "managedidentity"
    AzureWebJobsStorage__clientId             = var.identity_client_id
    APPLICATIONINSIGHTS_AUTHENTICATION_STRING = "Authorization=AAD;ClientId=${var.identity_client_id}"
    APPLICATIONINSIGHTS_CONNECTION_STRING     = var.app_insights_connection_string
  }, var.app_settings)
}
