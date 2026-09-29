# Offline plan test: mocked provider, no Azure credentials, nothing created.
#   terraform init -backend=false && terraform test
mock_provider "azurerm" {
  mock_data "azurerm_client_config" {
    defaults = {
      tenant_id       = "00000000-0000-0000-0000-000000000001"
      subscription_id = "00000000-0000-0000-0000-000000000002"
      object_id       = "00000000-0000-0000-0000-000000000003"
    }
  }
}

run "dev_cost_min" {
  command = plan

  variables {
    environment = "dev"
  }

  assert {
    condition     = azurerm_resource_group.this.name == "rg-road-dev-eus2-001"
    error_message = "resource group must follow the CAF pattern"
  }

  assert {
    condition     = alltrue([for k in ["env", "owner", "project", "cost-center"] : contains(keys(azurerm_resource_group.this.tags), k)])
    error_message = "required tags missing"
  }

  assert {
    condition     = local.p.log_quota_gb == 1
    error_message = "dev must use the cost-min log cap"
  }
}

run "prod_standard" {
  command = plan

  variables {
    environment                = "prod"
    cost_profile               = "standard"
    key_vault_purge_protection = true
  }

  assert {
    condition     = azurerm_resource_group.this.name == "rg-road-prod-eus2-001"
    error_message = "prod resource group name"
  }
}
