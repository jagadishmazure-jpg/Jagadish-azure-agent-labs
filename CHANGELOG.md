# Changelog

Notable changes, newest first. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). There are no versioned releases, so entries are grouped by date.

## Unreleased

### Added

- `docs/best-practices.md`: cloud and agentic AI practices with honest status and links.
- Architecture decision records in `docs/adr/`.
- `SECURITY.md`, `CONTRIBUTING.md` and this changelog.

### Changed

- README sections follow one order: what, why, architecture, run, test, deploy, limits.

## 2026-09-29

### Added

- Terraform stack per lab (`labs/<lab>/infra/terraform`) with shared modules, CAF names, tags, dev/prod tfvars and offline `terraform test`; Key Vault and least-privilege role assignments beyond the Bicep.
- GitHub Actions `infra.yml` (matrix per lab), `deploy.yml` (dev -> prod, Bicep or Terraform, `lab` input, OIDC, gated by `DEPLOY_ENABLED`) and `teardown.yml`; `docs/deployment.md`.
- Five offline agent labs on Microsoft Agent Framework with Foundry mocks, eval gates, synthetic data and Bicep.
