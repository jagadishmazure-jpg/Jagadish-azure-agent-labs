# `labs/medical-eye-scan-multimodal/tests/`

Offline pytest suite for the medical eye scan lab (mocks and stand-ins only).

| File | What it does |
|---|---|
| [`conftest.py`](conftest.py) | Forces `LAB_MODE=offline` for every test in this folder. |
| [`test_eye_components.py`](test_eye_components.py) | Vision stand-in, RAG, OOD gate, reasoning and calibration. |
| [`test_eye_evals_infra.py`](test_eye_evals_infra.py) | Eval gate (and its failure without the OOD gate), README banner, agent card and Bicep. |
| [`test_eye_workflow.py`](test_eye_workflow.py) | End-to-end graph runs through the research desk. |
