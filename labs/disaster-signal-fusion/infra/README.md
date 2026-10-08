# `labs/disaster-signal-fusion/infra/`

Infrastructure for the disaster signal fusion lab: Bicep plus a Terraform twin. Compiled and validated in CI, never deployed.

| File | What it does |
|---|---|
| [`main.bicep`](main.bicep) | Compile-only Bicep for the lab's Azure resources (never deployed). `privateNetworking` (default `false`) puts Event Hubs behind a private endpoint in an NSG-protected VNet with public access off; Terraform: `private_networking`. |
| [`terraform/`](terraform/README.md) | see its README |
