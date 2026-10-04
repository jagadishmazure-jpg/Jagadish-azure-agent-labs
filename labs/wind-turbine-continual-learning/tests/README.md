# `labs/wind-turbine-continual-learning/tests/`

Offline pytest suite for the wind turbine continual learning lab (mocks and stand-ins only).

| File | What it does |
|---|---|
| [`conftest.py`](conftest.py) | Forces `LAB_MODE=offline` for every test in this folder. |
| [`test_turbine_components.py`](test_turbine_components.py) | Features, detectors, registry, episode memory, diagnosis and the promotion pipeline. |
| [`test_turbine_learning.py`](test_turbine_learning.py) | Memory is not learning: evaluation -> learning signal -> candidate lesson -> lesson gate -> context gating. |
| [`test_turbine_workflow.py`](test_turbine_workflow.py) | Workflow paths, episode memory, no retraining from the workflow, deny-listed promotion, eval gate, card and Bicep. |
