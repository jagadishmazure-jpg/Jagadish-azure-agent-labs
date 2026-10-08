# `modules/private-network`

Optional private networking for a lab: a VNet with a private-endpoint subnet behind an NSG (default rules), plus private DNS zones linked to the VNet. A lab calls it only when `private_networking = true`. Written and plan-tested offline; not deployed.

| File | What it does |
|---|---|
| [`main.tf`](main.tf) | Resources (and module calls for a root stack). |
| [`outputs.tf`](outputs.tf) | Values exported to the caller / the pipeline. |
| [`variables.tf`](variables.tf) | Inputs with types, defaults and validation rules. |
| [`versions.tf`](versions.tf) | Terraform and provider version constraints. |
