# `.github/workflows/`

GitHub Actions for this repo. `ci.yml` runs lint, agent-card drift, the secrets scan, gitleaks over the full history, the doc-drift check, the shared and per-lab tests with each lab's eval gate (matrix), and a Bicep compile. `codeql.yml` runs CodeQL; `infra.yml` runs Terraform checks; `deploy.yml` and `teardown.yml` are gated off until a subscription exists.

| File | What it does |
|---|---|
| [`ci.yml`](ci.yml) | Lint, agent cards, secrets, doc drift, shared tests, lab matrix with eval gates, Bicep build. A `secrets` job runs gitleaks over the full git history. |
| [`codeql.yml`](codeql.yml) | CodeQL for Python and for the workflow files (`actions`), on push, pull request and weekly. Results appear under Security -> Code scanning and do not fail the build. |
| [`deploy.yml`](deploy.yml) | Gated deploy, dev then prod with approval (off unless `DEPLOY_ENABLED` is true). |
| [`infra.yml`](infra.yml) | Terraform fmt, validate, offline tests, tflint and checkov per lab; plan when credentials exist. |
| [`teardown.yml`](teardown.yml) | Gated, manual teardown of a lab environment. |

**Supply chain.** Every third-party action is pinned to a full commit SHA with the version in a comment, and every workflow starts from `permissions: contents: read`; jobs that need more (OIDC sign-in, CodeQL uploads) ask for it themselves. Dependabot ([`../dependabot.yml`](../dependabot.yml)) proposes weekly grouped updates that move the SHA and the comment together, and `shared/tests/test_repo_docs.py::test_workflows_are_hardened` fails CI if an action is left unpinned.

**SBOM.** The `sbom` job in `ci.yml` writes an SPDX JSON bill of materials for the source tree on every run (artifact `sbom.spdx.json`).
