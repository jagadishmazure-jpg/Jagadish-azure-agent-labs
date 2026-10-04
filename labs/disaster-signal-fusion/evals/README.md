# `labs/disaster-signal-fusion/evals/`

The disaster signal fusion lab's eval gate. CI runs `run_eval.py` and fails the job on any regression.

| File | What it does |
|---|---|
| [`run_eval.py`](run_eval.py) | Eval gate: scores the lab on the gold sets, writes a JSON report and exits 1 if any threshold fails. |
| [`gold/`](gold/README.md) | see its README |
