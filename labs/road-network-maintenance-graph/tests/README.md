# `labs/road-network-maintenance-graph/tests/`

Offline pytest suite for the road network maintenance lab (mocks and stand-ins only).

| File | What it does |
|---|---|
| [`conftest.py`](conftest.py) | Forces `LAB_MODE=offline` for every test in this folder. |
| [`test_road_graph.py`](test_road_graph.py) | Graph workers and the budget harness. |
| [`test_road_workflow.py`](test_road_workflow.py) | Coordinator workflow end to end. |
