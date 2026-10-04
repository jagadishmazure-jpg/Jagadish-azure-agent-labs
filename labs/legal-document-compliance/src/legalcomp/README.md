# `labs/legal-document-compliance/src/legalcomp/`

The Python package for the legal document compliance lab. See the [lab README](../../README.md) for the full design.

| File | What it does |
|---|---|
| [`__init__.py`](__init__.py) | Legal / compliance document lab: contracts and policies -> clauses + tables -> uncertainty -> reviewer. |
| [`card.py`](card.py) | A2A agent card for this lab, exported to `control-plane/agent-cards/`. |
| [`classify.py`](classify.py) | Clause classification. |
| [`extract.py`](extract.py) | Deterministic parsing logic behind the MCP servers: layout lookup (Document Intelligence stand-in), clause segmentation by numbered headings, and table normalisation. |
| [`index.py`](index.py) | Clause chunks into the AI Search stand-in (hybrid: keyword + hashed-embedding vector). |
| [`mcp_servers.py`](mcp_servers.py) | Three MCP tool servers (in-process offline) with small, read-only tool surfaces. |
| [`model_selection.py`](model_selection.py) | Model / tool selection for each capability the lab needs. |
| [`models.py`](models.py) | Pydantic packets passed between MCP tools, agents and the reviewer. |
| [`reliability.py`](reliability.py) | Reliability agent: scores each page for OCR junk and rejects pages that cannot be trusted. |
| [`routing.py`](routing.py) | Router and auditor agents. |
| [`service.py`](service.py) | Compliance-desk facade: index clauses, run the document workflow and record the reviewer's decision. |
| [`workflow.py`](workflow.py) | MAF workflow for one document. |
