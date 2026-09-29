"""Gold-set evaluation helpers and the eval gate used by every lab's `evals/run_eval.py` and CI."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def precision_recall(predicted: Iterable[str], gold: Iterable[str]) -> tuple[float, float]:
    p, g = set(predicted), set(gold)
    tp = len(p & g)
    precision = tp / len(p) if p else (1.0 if not g else 0.0)
    recall = tp / len(g) if g else 1.0
    return precision, recall


def expected_calibration_error(confidences: list[float], correct: list[bool], bins: int = 5) -> float:
    if not confidences:
        return 0.0
    total, ece = len(confidences), 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        idx = [i for i, c in enumerate(confidences) if (lo < c <= hi) or (b == 0 and c == 0.0)]
        if not idx:
            continue
        acc = sum(correct[i] for i in idx) / len(idx)
        conf = sum(confidences[i] for i in idx) / len(idx)
        ece += len(idx) / total * abs(acc - conf)
    return ece


@dataclass(frozen=True)
class Threshold:
    metric: str
    op: str  # ">=" or "<="
    value: float

    def ok(self, observed: float) -> bool:
        return observed >= self.value if self.op == ">=" else observed <= self.value


@dataclass
class GateReport:
    lab: str
    metrics: dict[str, float]
    thresholds: list[Threshold]
    failures: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures

    def to_dict(self) -> dict[str, Any]:
        return {
            "lab": self.lab,
            "passed": self.passed,
            "metrics": {k: round(v, 4) for k, v in self.metrics.items()},
            "thresholds": [f"{t.metric} {t.op} {t.value}" for t in self.thresholds],
            "failures": self.failures,
        }


def gate(lab: str, metrics: dict[str, float], thresholds: list[Threshold], rows=None) -> GateReport:
    fails = []
    for t in thresholds:
        if t.metric not in metrics:
            fails.append(f"{t.metric}: missing")
        elif not t.ok(metrics[t.metric]):
            fails.append(f"{t.metric}={metrics[t.metric]:.4f} fails {t.op} {t.value}")
    return GateReport(lab, metrics, thresholds, fails, rows or [])


def write_report(report: GateReport, out_dir: str | Path = "evals-out") -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{report.lab}.json"
    path.write_text(json.dumps({**report.to_dict(), "rows": report.rows}, indent=2, default=str))
    return path


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
