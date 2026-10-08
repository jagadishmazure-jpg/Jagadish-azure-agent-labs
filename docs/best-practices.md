# Best practices: what is implemented and what is planned

A checklist of enterprise cloud and agentic AI practices for these labs. Each row links to the code that implements it and says honestly whether it is implemented, written but not deployed, or planned. Nothing here has been deployed to Azure.

**How to read the status column**

- **Implemented**: the code is in this repo and runs in the offline tests or in CI.
- **Written, not deployed**: the infrastructure or workflow code exists and passes validation (`bicep build`, `terraform validate` and `terraform test`, tflint, checkov, actionlint), but it has never run against a real Azure subscription.
- **Planned**: not in the repo yet. The note says what is missing.

## Enterprise cloud

| Practice | What this repo does | Status | Where |
|---|---|---|---|
| **Identity: OIDC and managed identity** | Each lab runs as one user-assigned managed identity; the Azure adapters use `DefaultAzureCredential` (a mocked identity offline). CI signs in with OIDC, no client secret. | Implemented (mocked); Azure written, not deployed | [`shared/labcore/identity.py`](../shared/labcore/identity.py), [`lab-foundation module`](../infra/terraform/modules/lab-foundation/README.md), [ADR 0003](adr/0003-oidc-and-managed-identity.md) |
| **Least privilege** | The Terraform stacks give each lab identity only the data-plane roles it needs (for example Search Index Data Reader, Cognitive Services OpenAI User, Storage Blob Data Contributor, Event Hubs Data Receiver, Maps Data Reader), scoped to single resources. Local (key) auth is off on the AI services. The Bicep declares the identity but not these roles. | Written, not deployed | [`example: disaster lab stack`](../labs/disaster-signal-fusion/infra/terraform/main.tf), [`infra/terraform`](../infra/terraform/README.md) |
| **Networking** | Public endpoints with Entra ID auth only. There is no VNet or private endpoint in these lab stacks. | Planned | [`infra/terraform`](../infra/terraform/README.md) |
| **Secrets** | No secrets in the repo; a secrets scan of the working tree and gitleaks over the full git history run in CI, and GitHub secret scanning with push protection is on; every lab stack gets a Key Vault in RBAC mode (purge protection in prod). | Implemented (scan); Key Vault written, not deployed | [`scripts/secrets_scan.py`](../scripts/secrets_scan.py), [`ci.yml`](../.github/workflows/ci.yml), [`keyvault module`](../infra/terraform/modules/keyvault/README.md), [`.env.example`](../.env.example) |
| **Supply chain** | Every third-party action is pinned to a commit SHA with a version comment; every workflow has top-level read-only `permissions`; Dependabot opens weekly grouped updates for pip, Actions and the five lab Terraform stacks; CodeQL scans Python and the workflows; Dependabot alerts and security updates are on; `main` has a ruleset that blocks force-push and deletion and requires CI on pull requests. No SBOM yet. | Implemented; SBOM planned | [`dependabot.yml`](../.github/dependabot.yml), [`codeql.yml`](../.github/workflows/codeql.yml), [`SECURITY.md`](../SECURITY.md) |
| **Tagging and naming** | CAF names (`rg-dsf-dev-eus2-001`, one resource group per lab and environment) and six required tags, checked by `terraform test` in every lab. | Implemented (tests); written, not deployed | [`naming module`](../infra/terraform/modules/naming/README.md) |
| **Cost controls** | Dev uses the cost-min profile: free or basic SKUs where they exist, a 1 GB/day log cap and minimum model capacity. Each lab can be created and deleted on its own. Budgets and cost alerts are not defined yet. | Written, not deployed; budgets planned | [`example dev.tfvars`](../labs/disaster-signal-fusion/infra/terraform/envs/dev.tfvars) |
| **Infrastructure as code** | Each lab has Bicep and a Terraform stack; shared Terraform modules. CI builds every Bicep file and runs fmt, validate, offline `terraform test`, tflint and checkov per lab. | Implemented | [`infra/terraform`](../infra/terraform/README.md), [`.github/workflows/infra.yml`](../.github/workflows/infra.yml), [ADR 0001](adr/0001-bicep-and-terraform.md) |
| **CI/CD gates** | Lint, agent-card drift, secrets scan, gitleaks, shared tests, then per-lab tests and eval gates on every push. Deploy goes dev -> prod per lab through a GitHub Environment meant to require reviewers; it is gated off and the Environments do not exist yet. | Implemented (CI); deploy written, not deployed | [`.github/workflows/ci.yml`](../.github/workflows/ci.yml), [deployment.md](deployment.md), [ADR 0005](adr/0005-deploy-gated-off.md) |
| **Observability** | OpenTelemetry spans per workflow step (console exporter offline, App Insights in Azure mode); each lab stack creates Log Analytics and App Insights. No alerts or dashboards yet. | Implemented (spans); export written, not deployed | [`shared/labcore/tracing.py`](../shared/labcore/tracing.py), [`lab-foundation module`](../infra/terraform/modules/lab-foundation/README.md) |
| **Disaster recovery** | Labs are disposable: everything can be recreated from IaC and synthetic fixtures. Key Vault soft delete and purge protection in prod. No backup or second region. | Planned | [`keyvault module`](../infra/terraform/modules/keyvault/README.md) |

## Agentic AI

| Practice | What this repo does | Status | Where |
|---|---|---|---|
| **Human in the loop** | Every lab ends in a MAF `request_info` human review: officer, ophthalmologist, engineer, legal reviewer or technician. The safety rules (no public alert, no EHR write-back, no work order, no signing, no silent retraining) are enforced in code and checked by evals. | Implemented | [`shared/labcore/hitl.py`](../shared/labcore/hitl.py), [`lab table`](../README.md#the-labs) |
| **Evals and release gates** | Each lab has a gold set and an eval gate that fails CI on regression (precision/recall, calibration error, closure replay, lesson gain, ...). | Implemented | [`scripts/run_all_evals.py`](../scripts/run_all_evals.py), [`shared/labcore/evals.py`](../shared/labcore/evals.py), [ADR 0004](adr/0004-eval-gates-block-release.md) |
| **Guardrails and runtime safety** | Middleware adds retries, schema validation, deny-listed tools and a step budget; model output is validated and falls back to a deterministic draft; the eye-scan lab denies out-of-distribution inputs and abstains. | Implemented | [`shared/labcore/middleware.py`](../shared/labcore/middleware.py), [`eye-scan lab`](../labs/medical-eye-scan-multimodal/README.md) |
| **Tool governance and MCP** | Tools are MCP servers behind a gateway with a managed-identity role check and a deny-list; agent cards are generated and drift-checked in CI. | Implemented | [`shared/labcore/mcp_gateway.py`](../shared/labcore/mcp_gateway.py), [`agent cards`](../control-plane/agent-cards) |
| **Memory** | The turbine lab keeps episodic memory of past diagnoses and turns them into lessons that are used only after an eval gate promotes them. | Implemented | [`turbine lab`](../labs/wind-turbine-continual-learning/README.md) |
| **Grounding** | Hybrid retrieval (BM25 + vector + RRF) over lab corpora; the eye-scan explainer cites case ids and the legal lab cites clause ids, and citation validity is an eval metric. | Implemented | [`shared/labcore/search.py`](../shared/labcore/search.py), [`legal lab`](../labs/legal-document-compliance/README.md) |
| **Tracing** | One span per workflow step and tool call, with lab and run ids. | Implemented | [`shared/labcore/tracing.py`](../shared/labcore/tracing.py) |
| **Model versioning** | The Foundry model name, version and SKU (DataZoneStandard) are pinned as IaC variables; the turbine lab promotes a new detector or lesson only through a gate; the legal lab has an explicit model selection rule (best quality within latency and cost ceilings; most candidate scores are illustrative mocks). | Implemented; model pins written, not deployed | [`foundry-account module`](../infra/terraform/modules/foundry-account/README.md), [`labs/wind-turbine-continual-learning/src/turbine_cl/promotion.py`](../labs/wind-turbine-continual-learning/src/turbine_cl/promotion.py), [`labs/legal-document-compliance/src/legalcomp/model_selection.py`](../labs/legal-document-compliance/src/legalcomp/model_selection.py) |
| **Responsible AI** | The medical lab is labelled not a medical device; per-feature contribution scores explain the eye-scan and turbine outputs; all data is synthetic; each lab README lists its limitations. | Implemented | [`shared/labcore/explain.py`](../shared/labcore/explain.py), [`honest note`](../README.md#honest-note-on-mocks) |

## Known gaps, in priority order

- Provision one lab (the cheapest) in dev from the pipeline and run its smoke test.
- Private endpoints for the data and AI services in a prod profile.
- Deploy lab code as Functions or Container Apps jobs; today only the resources are provisioned.
- Budgets and cost alerts per lab resource group.

Related: [architecture decisions](adr/README.md) · [deployment pipeline](deployment.md) · [security policy](../SECURITY.md) · [contributing](../CONTRIBUTING.md)
