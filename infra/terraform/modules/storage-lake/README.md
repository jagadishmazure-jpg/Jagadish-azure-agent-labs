# `modules/storage-lake`

ADLS Gen2 storage (hierarchical namespace) with shared keys, local users and public blob access disabled; blob soft delete; `Storage Blob Data Contributor` for the identity.

| File | What it does |
|---|---|
| [`main.tf`](main.tf) | Resources (and module calls for a root stack). |
| [`outputs.tf`](outputs.tf) | Values exported to the caller / the pipeline. |
| [`variables.tf`](variables.tf) | Inputs with types, defaults and validation rules. |
| [`versions.tf`](versions.tf) | Terraform and provider version constraints. |
