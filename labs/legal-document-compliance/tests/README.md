# `labs/legal-document-compliance/tests/`

Offline pytest suite for the legal document compliance lab (mocks and stand-ins only).

| File | What it does |
|---|---|
| [`conftest.py`](conftest.py) | Forces `LAB_MODE=offline` for every test in this folder. |
| [`test_legal_components.py`](test_legal_components.py) | MCP servers, reliability scoring, extraction and classification. |
| [`test_legal_router_auditor.py`](test_legal_router_auditor.py) | Router, auditor (redo / escalate), compliance checklist and model selection. |
| [`test_legal_workflow.py`](test_legal_workflow.py) | End-to-end documents, junk pages, reviewer relabel, taxonomy and table checks, eval gate, card and Bicep. |
