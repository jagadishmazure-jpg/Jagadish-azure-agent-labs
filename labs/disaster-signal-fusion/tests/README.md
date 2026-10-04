# `labs/disaster-signal-fusion/tests/`

Offline pytest suite for the disaster signal fusion lab (mocks and stand-ins only).

| File | What it does |
|---|---|
| [`conftest.py`](conftest.py) | Forces `LAB_MODE=offline` for every test in this folder. |
| [`test_dsf_agents.py`](test_dsf_agents.py) | Specialist agents and the Bayesian coordinator, tested without the workflow. |
| [`test_dsf_evals_infra.py`](test_dsf_evals_infra.py) | Eval gate passes, catches a fusion that ignores rain; agent card current; Bicep compiles. |
| [`test_dsf_workflow.py`](test_dsf_workflow.py) | End-to-end runs of the MAF graph through the ops-desk facade. |
