"""Eval gate for the eye-scan research lab (offline, deterministic, synthetic labels).

    python labs/medical-eye-scan-multimodal/evals/run_eval.py [--out evals-out]

* top1_accuracy: top hypothesis vs the synthetic label on the held-out test split
* ece: expected calibration error of the top hypothesis' confidence (5 bins)
* ood_deny_rate: every out-of-distribution scan must be denied before reasoning
* false_deny_rate: in-distribution test scans wrongly denied
* citation_validity: every explanation cites only retrieved case ids (and at least one)
* ehr_writes: must stay 0 (the lab has no EHR path; the metric proves nothing slipped in)"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "src"), str(HERE.parents[2] / "shared")]

from eyescan.service import ResearchDesk  # noqa: E402
from labcore.evals import Threshold, expected_calibration_error, gate, write_report  # noqa: E402
from labcore.hitl import Decision  # noqa: E402

THRESHOLDS = [
    Threshold("top1_accuracy", ">=", 0.85),
    Threshold("ece", "<=", 0.15),
    Threshold("ood_deny_rate", ">=", 1.0),
    Threshold("false_deny_rate", "<=", 0.05),
    Threshold("citation_validity", ">=", 1.0),
    Threshold("ehr_writes", "<=", 0),
]


async def evaluate():
    desk = ResearchDesk()
    test = json.loads((HERE / "gold" / "test_cases.json").read_text())
    ood = json.loads((HERE / "gold" / "ood_cases.json").read_text())
    rows, conf, correct = [], [], []
    denied_in = cite_ok = ehr = 0
    for c in test:
        res = await desk.triage(c)
        if res.pending is None:
            denied_in += 1
            rows.append({"case": c["case_id"], "denied": True})
            continue
        top = res.pending.hypotheses[0]
        conf.append(top["confidence"])
        correct.append(top["label"] == c["label"])
        cited = set(res.pending.report["cited_case_ids"])
        cite_ok += bool(cited) and cited <= set(res.pending.similar_case_ids)
        out = (await desk.decide(res.run_id, res.request_id, Decision(True, "eval-reader"))).output
        ehr += bool(out["ehr_written"])
        rows.append(
            {"case": c["case_id"], "label": c["label"], "top": top["label"], "confidence": top["confidence"]}
        )
    ood_denied = 0
    for c in ood:
        res = await desk.triage(c)
        d = res.output is not None and res.output["status"] == "denied_out_of_distribution"
        ood_denied += d
        rows.append({"case": c["case_id"], "ood_denied": d, "reasons": res.output["reasons"] if d else []})
    answered = len(conf) or 1
    metrics = {
        "top1_accuracy": sum(correct) / answered,
        "ece": expected_calibration_error(conf, correct),
        "ood_deny_rate": ood_denied / len(ood),
        "false_deny_rate": denied_in / len(test),
        "citation_validity": cite_ok / answered,
        "ehr_writes": float(ehr),
        "mean_confidence": sum(conf) / answered,
    }
    return gate("medical-eye-scan-multimodal", metrics, THRESHOLDS, rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="evals-out")
    a = ap.parse_args(argv)
    report = asyncio.run(evaluate())
    path = write_report(report, a.out)
    print(json.dumps(report.to_dict(), indent=2))
    print(f"report: {path}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
