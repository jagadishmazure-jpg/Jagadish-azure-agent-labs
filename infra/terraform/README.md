# `infra/terraform`: shared Terraform modules for the labs

Each lab keeps its own stack next to its Bicep (`labs/<lab>/infra/terraform`, one resource group per lab and environment) so a lab can be created or deleted alone. The stacks share the modules in this folder.

| Lab stack | Workload | Modules used |
|---|---|---|
| [`disaster-signal-fusion`](../../labs/disaster-signal-fusion/infra/terraform/README.md) | `dsf` | `eventhubs`, `foundry-account`, `function-consumption`, `lab-foundation`, `maps`, `search`, `storage-lake` |
| [`legal-document-compliance`](../../labs/legal-document-compliance/infra/terraform/README.md) | `legal` | `cognitive`, `containerapps-env`, `foundry-account`, `lab-foundation`, `search`, `storage-lake` |
| [`medical-eye-scan-multimodal`](../../labs/medical-eye-scan-multimodal/infra/terraform/README.md) | `eye` | `foundry-account`, `lab-foundation`, `search`, `storage-lake` |
| [`road-network-maintenance-graph`](../../labs/road-network-maintenance-graph/infra/terraform/README.md) | `road` | `containerapps-env`, `foundry-account`, `lab-foundation`, `storage-lake` |
| [`wind-turbine-continual-learning`](../../labs/wind-turbine-continual-learning/infra/terraform/README.md) | `wtg` | `cosmos`, `eventhubs`, `foundry-account`, `lab-foundation`, `storage-lake` |

**Beyond the Bicep, on purpose:** every lab stack also creates a Key Vault (RBAC mode, purge protection in prod) and explicit least-privilege role assignments for the lab identity (for example `Search Index Data Reader`, `Cognitive Services OpenAI User`, `Storage Blob Data Contributor`). The Bicep templates only declare the identity.

## Bicep or Terraform?

Both toolchains describe the same resources, so the choice is about the client, not the design:

| Pick Bicep when | Pick Terraform when |
|---|---|
| The estate is Azure-only and the team already uses `azd`, ARM deployment history and Azure Policy. | The client already runs Terraform (platform team, module registry, Terraform Cloud / Enterprise, Spacelift, Atlantis). |
| You need a new resource API version the day it ships (Bicep types come straight from the ARM specs). | Several clouds or SaaS providers (GitHub, Entra, Datadog) must be managed from one workflow. |
| You want no state file to secure: ARM is the source of truth, `what-if` previews changes. | Reviewers want a `plan` in every pull request and state-based drift detection. |

Trade-offs to state up front:

- **State.** Terraform needs a secured remote state (here: Azure Storage with Entra ID auth, no account keys). Bicep has none to lose or leak, but it also has no drift report beyond `what-if`.
- **New features.** `azurerm` lags new Azure APIs by weeks. The `azapi` provider fills that gap by calling ARM directly with the same API versions Bicep uses; it is used here only where needed.
- **One source of truth per environment.** Pick one tool per environment and stay with it. Both tools can target the same subscription, but they must never manage the same resource group, or each will try to undo the other's changes.

## Naming, tags and the cost-min profile

- **Names** follow the Cloud Adoption Framework pattern `<type>-<workload>-<env>-<region>-<instance>`, for example `rg-dsf-dev-eus2-001`. Key Vault drops the region (24-character limit); ACR and Storage use the alphanumeric form. Set `name_suffix` when forking so globally unique names don't collide.
- **Tags** on every resource group and resource: `env`, `owner`, `project`, `cost-center`, plus `workload` and `managed-by`. Override `owner` / `cost_center` per client in the tfvars.
- **Profiles.** `envs/dev.tfvars` selects the cost-min profile (free / basic SKUs where they exist, 1 GB/day log cap, capacity 10 for the model deployment). `envs/prod.tfvars` selects the hardened/always-on shape (standard SKUs, higher model capacity, no log cap, Key Vault purge protection). Check the SKUs against the client's pricing agreement before any apply.

## Remote state (one-time bootstrap)

`backend.tf` is a partial `azurerm` backend. Create the storage once per subscription (or per client landing zone), with shared keys off so only Entra ID principals can read state:

```bash
az group create -n rg-tfstate-shared-eus2-001 -l eastus2 --tags env=shared owner=<you> project=tfstate cost-center=<cc>
az storage account create -n <globally-unique-name> -g rg-tfstate-shared-eus2-001 -l eastus2 \
  --sku Standard_ZRS --min-tls-version TLS1_2 --allow-blob-public-access false --allow-shared-key-access false
az storage container create --account-name <name> -n tfstate --auth-mode login
# the deploying identity needs "Storage Blob Data Contributor" on the container
```

Then pass the names at init (the pipeline reads them from the `TFSTATE_RESOURCE_GROUP` / `TFSTATE_STORAGE_ACCOUNT` variables):

```bash
terraform init -backend-config=envs/dev.backend.hcl \
  -backend-config=resource_group_name=rg-tfstate-shared-eus2-001 -backend-config=storage_account_name=<name>
```

## Validate locally (no Azure needed)

```bash
terraform init -backend=false
terraform fmt -check -recursive
terraform validate
terraform test          # plans with mocked providers and checks names, tags and profile shape
tflint --init && tflint --recursive
checkov -d . --config-file ../../.checkov.yaml
```

**Status:** validated offline only (the commands above run in CI on every pull request). No `apply` has been run: there is no Azure subscription yet.

## Files

| File | What it does |
|---|---|
| [`modules/`](modules/README.md) | Shared modules (one per resource family). |
| [`.tflint.hcl`](.tflint.hcl) | tflint configuration (terraform recommended preset + azurerm ruleset). |
