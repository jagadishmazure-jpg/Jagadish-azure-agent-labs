# `modules/lab-foundation`

What every lab needs: one user-assigned identity, Log Analytics, keyless App Insights (with `Monitoring Metrics Publisher`), and a Key Vault the identity can read.

| File | What it does |
|---|---|
| [`main.tf`](main.tf) | Resources (and module calls for a root stack). |
| [`outputs.tf`](outputs.tf) | Values exported to the caller / the pipeline. |
| [`variables.tf`](variables.tf) | Inputs with types, defaults and validation rules. |
| [`versions.tf`](versions.tf) | Terraform and provider version constraints. |
