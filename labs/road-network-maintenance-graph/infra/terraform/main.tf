# road-network-maintenance-graph: Terraform mirror of ../main.bicep (same resources, keyless everywhere, one
# user-assigned workload identity) plus a Key Vault and least-privilege role assignments.
data "azurerm_client_config" "current" {}

module "naming" {
  source      = "../../../../infra/terraform/modules/naming"
  workload    = var.workload
  environment = var.environment
  location    = var.location
  instance    = var.instance
  suffix      = var.name_suffix
}

resource "azurerm_resource_group" "this" {
  name     = module.naming.resource_group
  location = var.location
  tags     = local.tags
}

module "foundation" {
  source                     = "../../../../infra/terraform/modules/lab-foundation"
  resource_group_name        = azurerm_resource_group.this.name
  location                   = var.location
  tags                       = local.tags
  identity_name              = local.n["id"]
  log_analytics_name         = module.naming.log_analytics
  app_insights_name          = module.naming.app_insights
  key_vault_name             = module.naming.key_vault
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  daily_quota_gb             = local.p.log_quota_gb
  key_vault_purge_protection = var.key_vault_purge_protection
}

module "storage" {
  source                         = "../../../../infra/terraform/modules/storage-lake"
  resource_group_name            = azurerm_resource_group.this.name
  location                       = var.location
  tags                           = local.tags
  name                           = module.naming.storage_account
  blob_contributor_principal_ids = { workload = module.foundation.identity_principal_id }
}

module "aca_env" {
  source                     = "../../../../infra/terraform/modules/containerapps-env"
  resource_group_name        = azurerm_resource_group.this.name
  location                   = var.location
  tags                       = local.tags
  name                       = module.naming.container_apps_env
  log_analytics_workspace_id = module.foundation.log_analytics_id
}

module "foundry" {
  source                = "../../../../infra/terraform/modules/foundry-account"
  resource_group_name   = azurerm_resource_group.this.name
  location              = var.location
  tags                  = local.tags
  name                  = local.n["aif"]
  identity_id           = module.foundation.identity_id
  identity_principal_id = module.foundation.identity_principal_id
  deployment_name       = "road-plan-narrative"
  model_name            = var.narrative_model
  model_version         = var.model_version
  capacity              = local.p.capacity
}
