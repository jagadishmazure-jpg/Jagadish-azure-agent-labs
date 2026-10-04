# `labs/disaster-signal-fusion/src/signal_fusion/`

The Python package for the disaster signal fusion lab. See the [lab README](../../README.md) for the full design.

| File | What it does |
|---|---|
| [`__init__.py`](__init__.py) | Disaster signal fusion lab: seismic, satellite, weather and ground-displacement signals fused into flood / earthquake / tsunami risk for an operations desk. |
| [`agents.py`](agents.py) | The five specialist agents. |
| [`card.py`](card.py) | A2A agent card for this lab, exported to `control-plane/agent-cards/`. |
| [`functions.py`](functions.py) | Feature and quality jobs written like Azure Functions Event Hub-triggered handlers. |
| [`geo.py`](geo.py) | Azure Maps stand-in over a local GeoJSON file: region polygons, facility points, point-in-polygon, neighbours by centroid distance and exposure. |
| [`models.py`](models.py) | Pydantic packets for raw events, curated signals, agent findings and the ops-desk review. |
| [`risk.py`](risk.py) | Risk scoring, geospatial exposure and the emergency decision-support packet. |
| [`service.py`](service.py) | Ops-desk facade: publish readings to the Event Hub stand-in, assess a region, record the decision. |
| [`summary.py`](summary.py) | The only model-written text in this lab: a situation summary for the ops desk (Foundry, mocked). |
| [`workflow.py`](workflow.py) | The MAF workflow. |
