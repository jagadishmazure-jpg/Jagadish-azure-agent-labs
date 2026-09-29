# What every lab needs: one user-assigned workload identity, Log Analytics + keyless App Insights,
# and a Key Vault (RBAC mode) the identity can read secrets from.
resource "azurerm_user_assigned_identity" "this" {
  name                = var.identity_name
  resource_group_name = var.resource_group_name
  location            = var.location
  tags                = var.tags
}

resource "azurerm_log_analytics_workspace" "this" {
  name                = var.log_analytics_name
  resource_group_name = var.resource_group_name
  location            = var.location
  tags                = var.tags
  sku                 = "PerGB2018"
  retention_in_days   = 30
  daily_quota_gb      = var.daily_quota_gb
}

resource "azurerm_application_insights" "this" {
  name                         = var.app_insights_name
  resource_group_name          = var.resource_group_name
  location                     = var.location
  tags                         = var.tags
  application_type             = "web"
  workspace_id                 = azurerm_log_analytics_workspace.this.id
  local_authentication_enabled = false # ingestion via Entra ID (APPLICATIONINSIGHTS_AUTHENTICATION_STRING)
}

resource "azurerm_role_assignment" "metrics_publisher" {
  scope                            = azurerm_application_insights.this.id
  role_definition_name             = "Monitoring Metrics Publisher"
  principal_id                     = azurerm_user_assigned_identity.this.principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

module "keyvault" {
  source                      = "../keyvault"
  resource_group_name         = var.resource_group_name
  location                    = var.location
  tags                        = var.tags
  name                        = var.key_vault_name
  tenant_id                   = var.tenant_id
  purge_protection_enabled    = var.key_vault_purge_protection
  secret_reader_principal_ids = { workload = azurerm_user_assigned_identity.this.principal_id }
}
