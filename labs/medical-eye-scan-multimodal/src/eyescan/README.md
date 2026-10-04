# `labs/medical-eye-scan-multimodal/src/eyescan/`

The Python package for the medical eye scan lab. See the [lab README](../../README.md) for the full design.

| File | What it does |
|---|---|
| [`__init__.py`](__init__.py) | Retinal-scan research triage lab. |
| [`card.py`](card.py) | A2A agent card for this lab, exported to `control-plane/agent-cards/`. |
| [`explainer.py`](explainer.py) | Explainer (Foundry, mocked): turns the computed hypotheses into a short research report that must cite the retrieved case ids and reference notes, and must carry the not-a-medical-device banner. |
| [`knowledge.py`](knowledge.py) | RAG over the labeled case library and the reference-report notes (AI Search stand-in, hybrid: keyword over report + metadata words, vector over standardised image features). |
| [`models.py`](models.py) | Packets for the scan graph. |
| [`reasoning.py`](reasoning.py) | Constrained reasoning: hypotheses may only come from the fixed label set, every hypothesis must be supported by retrieved labeled cases, and confidence is temperature-calibrated on a held-out calibration split. |
| [`service.py`](service.py) | Research-desk facade. |
| [`vision.py`](vision.py) | Azure AI Vision / Foundry vision stand-in: deterministic, hand-written feature extraction on the 16x16 synthetic arrays, plus a text embedding of the report / metadata (feature hashing). |
| [`workflow.py`](workflow.py) | MAF workflow: Scans -> RAG -> Reasoning -> Explain -> ophthalmologist review. |
