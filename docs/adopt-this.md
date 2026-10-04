# Adopt this

A checklist for reusing these labs' patterns in your own agent system. Each item points at the code that shows it.

## Minimum set (do these first)

| # | Practice | Where it is shown |
|---|---|---|
| 1 | One mode switch; Azure adapters raise until wired | `shared/labcore/config.py` |
| 2 | Side-effecting tools denied to agents and left to a named human | `shared/labcore/middleware.py`, `shared/labcore/hitl.py` |
| 3 | Tool output validated against a schema before the model sees it | `validate_tool_result` |
| 4 | Facts computed in code; the model only rewords under a schema with a fallback | `FoundryWriter` |
| 5 | Data-zone policy checked before a model client exists | `ZonePolicy` |
| 6 | Gold set and eval gate in CI, thresholds published in the agent card | `labs/*/evals/`, `labs/*/src/*/card.py` |
| 7 | Step budget on every graph | `RunState` |
| 8 | Managed identity only; no keys anywhere | `identity.py`, `disableLocalAuth` in Bicep |

## Then

- Put MCP servers behind a gateway that checks a deny-list, a tool allow-list and an app role per tool ([mcp-gateway](components/mcp-gateway.md)).
- Use separate consumer groups for processing and audit on event streams ([search-and-streams](components/search-and-streams.md)).
- Let learning change behavior only through a promotion gate that a human triggers (wind-turbine lab).
- Generate doc excerpts and outputs from code and fail CI on drift (`scripts/doc_drift.py`).

## Per-lab "Adopt this"

Each lab README ends with its own steps:

| Lab | Pattern worth taking |
|---|---|
| [disaster-signal-fusion](../labs/disaster-signal-fusion/README.md) | parallel signal branches fused by a Bayesian coordinator; advice only |
| [legal-document-compliance](../labs/legal-document-compliance/README.md) | router plus auditor with redo and escalate |
| [medical-eye-scan-multimodal](../labs/medical-eye-scan-multimodal/README.md) | calibrated confidence, OOD denial and abstention |
| [road-network-maintenance-graph](../labs/road-network-maintenance-graph/README.md) | graph analytics as tools with a budget guard |
| [wind-turbine-continual-learning](../labs/wind-turbine-continual-learning/README.md) | episodic memory and eval-gated lessons |

## What not to copy as is

- The stand-ins: they model behavior, not service limits.
- Public network access on some services: add private endpoints.
- Retries without backoff: real adapters need jittered exponential backoff.
