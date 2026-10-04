# `shared/labcore/`

The shared layer every lab uses: one config switch, MCP gateway, middleware, Foundry zone policy, search and stream stand-ins, tracing, eval gate and HITL helpers. See [docs/components/labcore.md](../../docs/components/labcore.md).

| File | What it does |
|---|---|
| [`__init__.py`](__init__.py) | labcore: the reusable layers every lab is built on (config switch, tracing, Foundry client, MAF middleware, MCP gateway with managed identity, workflow helpers, eval gate). |
| [`cards.py`](cards.py) | Agent cards in the A2A card shape (plain JSON, no a2a-sdk dependency). |
| [`config.py`](config.py) | One switch for every adapter: `LAB_MODE=offline` (default) or `LAB_MODE=azure`. |
| [`evals.py`](evals.py) | Gold-set evaluation helpers and the eval gate used by every lab's `evals/run_eval.py` and CI. |
| [`explain.py`](explain.py) | Per-feature contribution scores for a single prediction. |
| [`foundry.py`](foundry.py) | Azure AI Foundry access, mocked. |
| [`hitl.py`](hitl.py) | Human-in-the-loop types. |
| [`identity.py`](identity.py) | Managed identity, mocked. |
| [`infra_check.py`](infra_check.py) | Compile a lab's Bicep with the local Bicep CLI (never deploys). |
| [`mcp_gateway.py`](mcp_gateway.py) | One path from agents to MCP tool servers: allow-list, deny-list, managed-identity token check, retries on transient errors, result schema validation and a span per call. |
| [`middleware.py`](middleware.py) | MAF middleware and harness helpers shared by the labs. |
| [`search.py`](search.py) | Azure AI Search stand-in: an in-memory index with keyword (BM25-style), vector (cosine) and hybrid (reciprocal rank fusion) queries plus equality filters. |
| [`streams.py`](streams.py) | Event Hubs and ADLS Gen2 stand-ins shared by the streaming labs. |
| [`tracing.py`](tracing.py) | OpenTelemetry tracing. |
| [`workflow.py`](workflow.py) | Helpers around MAF workflows: a node base class with a step budget and a span per node, and a runner that returns either the final output or the pending human-review request. |
