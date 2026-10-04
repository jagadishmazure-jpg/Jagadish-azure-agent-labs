# `labs/road-network-maintenance-graph/src/roadgraph/`

The Python package for the road network maintenance lab. See the [lab README](../../README.md) for the full design.

| File | What it does |
|---|---|
| [`__init__.py`](__init__.py) | Road network maintenance lab: a coordinator and graph workers plan repairs on a synthetic city. |
| [`card.py`](card.py) | A2A agent card for this lab, exported to `control-plane/agent-cards/`. |
| [`graph_ops.py`](graph_ops.py) | Graph work done by the agents, in flow order (topology -> paths -> priority -> impact). |
| [`harness.py`](harness.py) | Budget harness. |
| [`models.py`](models.py) | Plan request and the run state passed through the graph. |
| [`narrative.py`](narrative.py) | Plan narrative for the city engineer (Foundry, mocked). |
| [`service.py`](service.py) | Planning-desk facade: start a plan run and record the engineer's decision. |
| [`workflow.py`](workflow.py) | Planning Coordinator + four graph agents on MAF. |
