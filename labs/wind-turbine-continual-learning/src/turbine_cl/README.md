# `labs/wind-turbine-continual-learning/src/turbine_cl/`

The Python package for the wind turbine continual learning lab. See the [lab README](../../README.md) for the full design.

| File | What it does |
|---|---|
| [`__init__.py`](__init__.py) | Wind turbine continual-learning lab: telemetry -> anomaly -> similar episodes -> diagnosis -> recommendation -> technician -> episode memory. |
| [`agents.py`](agents.py) | The six agents of the lab, in flow order: memory -> evals -> learning -> gating -> improve. |
| [`card.py`](card.py) | A2A agent card for this lab, exported to `control-plane/agent-cards/`. |
| [`context.py`](context.py) | Turbine context: fleet model per turbine, maintenance history and weather taken from telemetry. |
| [`detector.py`](detector.py) | Anomaly detectors and the read-only detector registry. |
| [`diagnose.py`](diagnose.py) | Diagnosis from similar episodes and a fixed action catalog; Foundry (mocked) writes the recommendation text, constrained to catalog actions and retrieved episode ids. |
| [`episodes.py`](episodes.py) | Episode memory: Cosmos DB (vector search) / AI Search stand-in. |
| [`features.py`](features.py) | Physics-informed residual features: what the turbine does minus what a healthy turbine would do at the same wind and ambient temperature. |
| [`lessons.py`](lessons.py) | Learned lessons: memory is not learning. |
| [`promotion.py`](promotion.py) | Eval-gated detector promotion. |
| [`service.py`](service.py) | Maintenance-desk facade: stream telemetry, run the diagnosis workflow and record the technician's decision. |
| [`workflow.py`](workflow.py) | MAF workflow for one turbine window. |
