# `scripts/`

Repository scripts used locally and in CI.

| File | What it does |
|---|---|
| [`component_demos.py`](component_demos.py) | Small, deterministic demos of the shared layer, used as the "Real output" of docs/components. |
| [`doc_drift.py`](doc_drift.py) | Doc-drift check: keep pasted output and code excerpts in the Markdown docs honest. |
| [`export_agent_cards.py`](export_agent_cards.py) | Render every lab's agent card into control-plane/agent-cards/. |
| [`overlap_check.py`](overlap_check.py) | Originality check: report any run of N consecutive words (default 8) that appears both in the repository's text files and in the given reference documents. |
| [`run_all_evals.py`](run_all_evals.py) | Run every lab's eval gate and print a summary table. |
| [`secrets_scan.py`](secrets_scan.py) | Minimal secrets scan over every tracked or to-be-tracked file. |
