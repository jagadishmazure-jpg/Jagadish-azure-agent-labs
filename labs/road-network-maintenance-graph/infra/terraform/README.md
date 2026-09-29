# `road-network-maintenance-graph`: Terraform stack

The Terraform mirror of [`../main.bicep`](../main.bicep) for this lab (workload code `road`), plus a Key Vault and least-privilege role assignments for the lab identity. Modules: [`containerapps-env`](../../../../infra/terraform/modules/containerapps-env/README.md), [`foundry-account`](../../../../infra/terraform/modules/foundry-account/README.md), [`lab-foundation`](../../../../infra/terraform/modules/lab-foundation/README.md), [`naming`](../../../../infra/terraform/modules/naming/README.md), [`storage-lake`](../../../../infra/terraform/modules/storage-lake/README.md).

```bash
terraform init -backend=false && terraform validate && terraform test   # offline, mocked provider
terraform plan -var-file=envs/dev.tfvars                                 # needs Azure login + backend
```

Names, tags, state and the Bicep-vs-Terraform choice are described in [`infra/terraform/README.md`](../../../../infra/terraform/README.md).

| File | What it does |
|---|---|
| [`envs/`](envs/README.md) | dev / prod tfvars and partial backend configs. |
| [`tests/`](tests/README.md) | Offline `terraform test` plans with a mocked provider. |
| [`.terraform.lock.hcl`](.terraform.lock.hcl) | Provider lock file (exact versions and checksums) so CI and laptops resolve the same providers. |
| [`.tflint.hcl`](.tflint.hcl) | tflint configuration (terraform recommended preset + azurerm ruleset). |
| [`backend.tf`](backend.tf) | Empty `azurerm` backend block (partial config); coordinates are passed with `-backend-config` at init. |
| [`locals.tf`](locals.tf) | Derived values: cost profile table, effective SKUs, the tag set, workload lists. |
| [`main.tf`](main.tf) | Resources (and module calls for a root stack). |
| [`outputs.tf`](outputs.tf) | Values exported to the caller / the pipeline. |
| [`providers.tf`](providers.tf) | Provider configuration. Credentials come from the environment (`az login` locally, OIDC in Actions); no secrets in code. |
| [`variables.tf`](variables.tf) | Inputs with types, defaults and validation rules. |
| [`versions.tf`](versions.tf) | Terraform and provider version constraints. |
