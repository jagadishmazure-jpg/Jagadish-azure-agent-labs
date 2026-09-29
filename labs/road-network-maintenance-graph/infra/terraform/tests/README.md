# `road-network-maintenance-graph` tests

`terraform test` plans against mocked providers (no credentials, nothing created) and checks the CAF names, tags and the dev / prod profile.

| File | What it does |
|---|---|
| [`plan.tftest.hcl`](plan.tftest.hcl) | Offline `terraform test`: plans with mocked providers and asserts naming, tags and the per-profile shape. No Azure credentials needed. |
