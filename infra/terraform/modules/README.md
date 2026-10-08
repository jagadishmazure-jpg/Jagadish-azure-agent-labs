# `infra/terraform/modules`

Shared modules used by every lab stack under `labs/<lab>/infra/terraform`. Each takes `resource_group_name`, `location` and `tags` and keeps local (key) auth off.

| File | What it does |
|---|---|
| [`cognitive/`](cognitive/README.md) | Single-purpose Cognitive Services account (Document Intelligence or Content Safety), keyless, with a custom subdomain. |
| [`containerapps-env/`](containerapps-env/README.md) | Container Apps managed environment on the Consumption workload profile, logging to Log Analytics; optional VNet integration. |
| [`cosmos/`](cosmos/README.md) | Cosmos DB for NoSQL, serverless, local auth disabled; database, containers, and the built-in data-contributor role for the given principals. |
| [`eventhubs/`](eventhubs/README.md) | Event Hubs namespace (Standard, local auth disabled), hubs, consumer groups and the data-receiver role. Optional private endpoint with public access off. |
| [`foundry-account/`](foundry-account/README.md) | Foundry (AIServices) account on the lab identity, keyless, one DataZoneStandard model deployment, and `Cognitive Services OpenAI User` for the identity. |
| [`function-consumption/`](function-consumption/README.md) | Linux Function App on the Consumption (Y1) plan running as the lab identity, with identity-based host storage. |
| [`keyvault/`](keyvault/README.md) | Key Vault in RBAC mode (no access policies), soft delete 7 days, purge protection as a variable, and `Key Vault Secrets User` for the given workload identities. |
| [`lab-foundation/`](lab-foundation/README.md) | What every lab needs: one user-assigned identity, Log Analytics, keyless App Insights (with `Monitoring Metrics Publisher`), and a Key Vault the identity can read. |
| [`maps/`](maps/README.md) | Azure Maps Gen2 account with shared-key auth disabled and `Azure Maps Data Reader` for the identity. |
| [`naming/`](naming/README.md) | CAF naming helper: `<type>-<workload>-<env>-<region>-<instance>` (for example `rg-agentplat-dev-eus2-001`), compressed forms for Key Vault (24 chars, region dropped), ACR and Storage (alphanumeric), and an optional suffix for globally unique names. No resources. |
| [`private-network/`](private-network/README.md) | Optional VNet with an NSG-protected private-endpoint subnet and linked private DNS zones (used by the Event Hubs labs when `private_networking = true`). |
| [`search/`](search/README.md) | Azure AI Search with API keys disabled (Entra ID only), system-assigned identity and the free semantic-ranker plan. |
| [`storage-lake/`](storage-lake/README.md) | ADLS Gen2 storage (hierarchical namespace) with shared keys, local users and public blob access disabled; blob soft delete; `Storage Blob Data Contributor` for the identity. |
