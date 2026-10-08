# Changelog

Notable changes, newest first. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). There are no versioned releases, so entries are grouped by milestone.

## Unreleased

### Added

- SBOM job in CI: an SPDX JSON software bill of materials of the source tree on every run (artifact `sbom.spdx.json`).
- Supply-chain hardening: every GitHub Action pinned to a commit SHA with a version comment, top-level `permissions` on every workflow, a gitleaks job in CI, a CodeQL workflow, `.github/dependabot.yml` and a guard test (`test_workflows_are_hardened`).
- GitHub settings: Dependabot alerts and security updates, private vulnerability reporting and a `main` ruleset (no force-push or deletion; CI required on pull requests).
- `docs/best-practices.md`: cloud and agentic AI practices with honest status and links.
- Architecture decision records in `docs/adr/`.
- `SECURITY.md`, `CONTRIBUTING.md` and this changelog.
- Lab READMEs in a 17-section format; `docs/components/` pages for the shared layer and infrastructure; `docs/implementation-guide.md` and `docs/adopt-this.md`.
- `scripts/doc_drift.py`: generated outputs and code excerpts in the docs, checked in CI; `scripts/component_demos.py`.
- A README with a file table in every folder, `.github/CODEOWNERS`, and `shared/tests/test_repo_docs.py`.

### Changed

- README sections follow one order: what, why, architecture, run, test, deploy, limits.
- Dates removed from ADRs and this changelog.

## Milestone 1

### Added

- Terraform stack per lab (`labs/<lab>/infra/terraform`) with shared modules, CAF names, tags, dev/prod tfvars and offline `terraform test`; Key Vault and least-privilege role assignments beyond the Bicep.
- GitHub Actions `infra.yml` (matrix per lab), `deploy.yml` (dev -> prod, Bicep or Terraform, `lab` input, OIDC, gated by `DEPLOY_ENABLED`) and `teardown.yml`; `docs/deployment.md`.
- Five offline agent labs on Microsoft Agent Framework with Foundry mocks, eval gates, synthetic data and Bicep.
