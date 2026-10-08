# Security policy

## Supported versions

Only the `main` branch is maintained. There are no released versions.

## Reporting a vulnerability

Please do not open a public issue with the details.

1. Use GitHub private vulnerability reporting: **Security** tab -> **Report a vulnerability** on [Jagadish-azure-agent-labs](https://github.com/jagadishmazure-jpg/Jagadish-azure-agent-labs/security).
2. If that button is not shown, open an issue titled `Security contact request` with no technical details, and I will reply with a private channel.

I aim to acknowledge a report within 5 working days. This is a personal portfolio maintained by one person, so there is no formal SLA or bug bounty.

## Scope

This repository is a demonstration. It runs offline against mocks and synthetic data and has never been deployed to a live Azure tenant. All data is synthetic. In scope: anything in the code, infrastructure definitions or workflows that would be unsafe if someone deployed it as written (for example, a role that is broader than documented, a secret that could leak through CI, or a guardrail that can be bypassed). Out of scope: the deterministic mocks and sandbox stand-ins themselves.

## What the repo already does

- No secrets in the repo; [`scripts/secrets_scan.py`](scripts/secrets_scan.py) checks the working tree and gitleaks checks the full git history, both in CI.
- CI signs in to Azure with OIDC only ([ADR 0003](docs/adr/0003-oidc-and-managed-identity.md)).
- One managed identity per lab with resource-scoped roles; local (key) auth disabled on AI services in the IaC.
- checkov scans every lab stack, with each skipped check justified in [`.checkov.yaml`](.checkov.yaml).
- Deny-listed tools, schema validation and human review in every lab workflow.
- **Threat model:** [`docs/security/threat-model.md`](docs/security/threat-model.md) maps STRIDE, the OWASP Top 10 for LLM Applications and MITRE ATLAS techniques to this repository's real components, with the control, the test that proves it and whether it is built, written but not deployed, or planned.
- **Supply chain:** every third-party GitHub Action is pinned to a full commit SHA with its version in a comment, and every workflow starts from read-only `permissions`. Dependabot proposes weekly, grouped updates ([`.github/dependabot.yml`](.github/dependabot.yml)); CodeQL scans the Python code and the workflow files ([`codeql.yml`](.github/workflows/codeql.yml)); gitleaks scans the full git history in CI. A test (`test_workflows_are_hardened`) fails if an action is left unpinned or a workflow loses its `permissions` block.
- **SBOM:** the `sbom` job in [`ci.yml`](.github/workflows/ci.yml) builds an SPDX JSON software bill of materials from the lockfiles and manifests on every run and keeps it as the `sbom.spdx.json` build artifact. The repository ships no container image, so there is no image scan or provenance step.
- **GitHub settings:** secret scanning with push protection, Dependabot alerts and security updates, private vulnerability reporting, and a ruleset on `main` that blocks force-pushes and branch deletion and requires the CI checks before a pull request can merge. The maintainer (repository admin) can still push directly to `main`, so for direct pushes the checks run after the push rather than before it.
- Full status of each control: [`docs/best-practices.md`](docs/best-practices.md).
