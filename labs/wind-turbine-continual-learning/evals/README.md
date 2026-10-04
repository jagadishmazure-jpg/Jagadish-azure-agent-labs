# `labs/wind-turbine-continual-learning/evals/`

The wind turbine continual learning lab's eval gate. CI runs `run_eval.py` and fails the job on any regression.

| File | What it does |
|---|---|
| [`run_eval.py`](run_eval.py) | Eval gate: scores the lab on the gold sets, writes a JSON report and exits 1 if any threshold fails. |
| [`gold/`](gold/README.md) | see its README |
