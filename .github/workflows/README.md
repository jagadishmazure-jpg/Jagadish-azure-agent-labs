# `.github/workflows/`

GitHub Actions for this repo. `ci.yml` runs lint, agent-card drift, the secrets scan, the doc-drift check, the shared and per-lab tests with each lab's eval gate (matrix), and a Bicep compile. `infra.yml` runs Terraform checks; `deploy.yml` and `teardown.yml` are gated off until a subscription exists.

| File | What it does |
|---|---|
| [`ci.yml`](ci.yml) | Lint, agent cards, secrets, doc drift, shared tests, lab matrix with eval gates, Bicep build. |
| [`deploy.yml`](deploy.yml) | Gated deploy, dev then prod with approval (off unless `DEPLOY_ENABLED` is true). |
| [`infra.yml`](infra.yml) | Terraform fmt, validate, offline tests, tflint and checkov per lab; plan when credentials exist. |
| [`teardown.yml`](teardown.yml) | Gated, manual teardown of a lab environment. |
