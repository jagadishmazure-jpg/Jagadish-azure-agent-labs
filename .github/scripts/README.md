# `.github/scripts`

Shell steps called by the deploy and teardown workflows.

| File | What it does |
|---|---|
| [`deploy.sh`](deploy.sh) | `provision` one lab (Terraform apply or Bicep `az deployment group create`), `smoke` (resources exist, Foundry endpoint answers, local auth disabled), `destroy`. |
