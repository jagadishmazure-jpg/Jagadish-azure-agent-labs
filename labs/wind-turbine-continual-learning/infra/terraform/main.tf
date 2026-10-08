# wind-turbine-continual-learning: Terraform mirror of ../main.bicep (same resources, keyless everywhere, one
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

module "eventhubs" {
  source                 = "../../../../infra/terraform/modules/eventhubs"
  resource_group_name    = azurerm_resource_group.this.name
  location               = var.location
  tags                   = local.tags
  name                   = local.n["evhns"]
  hubs                   = { turbine-telemetry = { partitions = 4, retention_days = 1 } }
  consumer_groups        = {}
  receiver_principal_ids = { workload = module.foundation.identity_principal_id }
  # Public stays the cheap default; private_networking locks the namespace to the VNet.
  public_network_access_enabled = !var.private_networking
  private_endpoint              = var.private_networking ? { subnet_id = module.network[0].pe_subnet_id, dns_zone_id = module.network[0].zone_ids["eventhubs"] } : null
}

module "cosmos" {
  source                         = "../../../../infra/terraform/modules/cosmos"
  resource_group_name            = azurerm_resource_group.this.name
  location                       = var.location
  tags                           = local.tags
  name                           = local.n["cosmos"]
  database_name                  = "turbine"
  containers                     = { episodes = { partition_key = "/turbine_id" } }
  data_contributor_principal_ids = { workload = module.foundation.identity_principal_id }
}

module "storage" {
  source                         = "../../../../infra/terraform/modules/storage-lake"
  resource_group_name            = azurerm_resource_group.this.name
  location                       = var.location
  tags                           = local.tags
  name                           = module.naming.storage_account
  blob_contributor_principal_ids = { workload = module.foundation.identity_principal_id }
}

module "foundry" {
  source                = "../../../../infra/terraform/modules/foundry-account"
  resource_group_name   = azurerm_resource_group.this.name
  location              = var.location
  tags                  = local.tags
  name                  = local.n["aif"]
  identity_id           = module.foundation.identity_id
  identity_principal_id = module.foundation.identity_principal_id
  deployment_name       = "turbine-diagnosis"
  model_name            = var.diagnosis_model
  model_version         = var.model_version
  capacity              = local.p.capacity
}

# ---- optional private networking for Event Hubs (off by default; not deployed) ----
module "network" {
  source              = "../../../../infra/terraform/modules/private-network"
  count               = var.private_networking ? 1 : 0
  resource_group_name = azurerm_resource_group.this.name
  location            = var.location
  tags                = local.tags
  name                = module.naming.vnet
  dns_zones           = { eventhubs = "privatelink.servicebus.windows.net" }
}
