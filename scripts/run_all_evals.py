"""Run every lab's eval gate and print a summary table. Exit 1 if any gate fails.

python scripts/run_all_evals.py [--out evals-out] [--lab <name>]"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LABS = [
    "disaster-signal-fusion",
    "medical-eye-scan-multimodal",
    "road-network-maintenance-graph",
    "legal-document-compliance",
    "wind-turbine-continual-learning",
]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="evals-out")
    ap.add_argument("--lab", choices=LABS)
    a = ap.parse_args(argv)
    failed = []
    for lab in [a.lab] if a.lab else LABS:
        proc = subprocess.run(
            [sys.executable, str(ROOT / "labs" / lab / "evals" / "run_eval.py"), "--out", a.out],
            capture_output=True,
            text=True,
        )
        report = json.loads((Path(a.out) / f"{lab}.json").read_text()) if proc.returncode in (0, 1) else {}
        status = "PASS" if proc.returncode == 0 else "FAIL"
        if proc.returncode:
            failed.append(lab)
            print(proc.stdout[-2000:], proc.stderr[-2000:])
        metrics = ", ".join(f"{k}={v}" for k, v in report.get("metrics", {}).items())
        print(f"{status}  {lab}: {metrics}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
