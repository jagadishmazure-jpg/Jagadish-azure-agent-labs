# Remote state in Azure Storage (Entra ID auth). Partial config, supplied at init:
#   terraform init -backend-config=envs/dev.backend.hcl
# Local validation skips it:  terraform init -backend=false
terraform {
  backend "azurerm" {}
}
