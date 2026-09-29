"""Eval gate for the wind-turbine continual-learning lab.

    python labs/wind-turbine-continual-learning/evals/run_eval.py [--out evals-out]

* heldout_recall / heldout_fpr: registered champion on held-out failure and normal windows
* diagnosis_accuracy: diagnosis from retrieved episodes vs the injected fault label (held-out failures)
* bad_candidates_rejected: the promotion pipeline must reject a noisy and an insensitive candidate
  (run against a temporary copy of the registry)
* registry_unchanged_by_agents: the registry file is byte-identical after every workflow run
* episodes_only_after_review: no episode is written before a technician decision
* lesson_learned_from_feedback: a technician correction yields a candidate lesson that passes the lesson gate
* overbroad_lesson_rejected: a lesson without its context conditions breaks held-out cases and is rejected
* lesson_gain: accuracy on the lesson eval set after promotion minus before (>= 0.10)
* gating_precision: the promoted lesson is applied only where turbine model + pattern fit (never on model A)
* safer_decision_after_learning: the next model-B drift case is diagnosed as sensor drift via the gated lesson,
  while the same reading on model A is left to memory (no negative transfer)"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "src"), str(HERE.parents[2] / "shared")]

from labcore.evals import Threshold, gate, write_report  # noqa: E402
from labcore.hitl import Decision  # noqa: E402
from turbine_cl import DATA, REGISTRY  # noqa: E402
from turbine_cl.agents import baseline_case_fn  # noqa: E402
from turbine_cl.lessons import LessonRegistry, applies, promote_lesson  # noqa: E402
from turbine_cl.promotion import evaluate_detector, promote  # noqa: E402
from turbine_cl.service import DiagnosticsDesk  # noqa: E402

THRESHOLDS = [
    Threshold("heldout_recall", ">=", 0.9),
    Threshold("heldout_fpr", "<=", 0.1),
    Threshold("diagnosis_accuracy", ">=", 0.85),
    Threshold("bad_candidates_rejected", ">=", 1.0),
    Threshold("registry_unchanged_by_agents", ">=", 1.0),
    Threshold("episodes_only_after_review", ">=", 1.0),
    Threshold("lesson_learned_from_feedback", ">=", 1.0),
    Threshold("overbroad_lesson_rejected", ">=", 1.0),
    Threshold("lesson_gain", ">=", 0.1),
    Threshold("gating_precision", ">=", 1.0),
    Threshold("safer_decision_after_learning", ">=", 1.0),
]
BAD = {
    "noisy": {"kind": "isolation_forest", "n_estimators": 100, "contamination": 0.2, "random_state": 7},
    "insensitive": {
        "kind": "isolation_forest",
        "n_estimators": 100,
        "contamination": 0.001,
        "random_state": 7,
    },
}


async def evaluate():
    before = hashlib.sha256(REGISTRY.read_bytes()).hexdigest()
    desk = DiagnosticsDesk()
    det, _entry = desk.detector
    scores = evaluate_detector(det)
    held = json.loads((HERE / "gold" / "heldout.json").read_text())
    rows, ok, n, early = [], 0, 0, 0
    for w in held:
        if w["label"] == "normal":
            continue
        desk.publish(w["rows"])
        written_before = len(desk.episodes.written)
        res = await desk.check(w["turbine_id"])
        early += len(desk.episodes.written) != written_before
        n += 1
        hit = res.pending is not None and res.pending.diagnosis == w["label"]
        ok += hit
        if res.pending is not None:
            await desk.decide(res.run_id, res.request_id, Decision(True, "eval-tech"))
        rows.append(
            {
                "kind": "diagnosis",
                "turbine": w["turbine_id"],
                "label": w["label"],
                "predicted": res.pending.diagnosis if res.pending else None,
            }
        )
    rejected = 0
    with tempfile.TemporaryDirectory() as tmp:
        reg = Path(tmp) / "registry.json"
        shutil.copy(REGISTRY, reg)
        for name, params in BAD.items():
            rec = promote(f"bad-{name}", params, "eval-gate", reg)
            rejected += rec["decision"] == "rejected"
            rows.append(
                {
                    "kind": "promotion",
                    "candidate": name,
                    "decision": rec["decision"],
                    "reasons": rec["reasons"],
                }
            )
    learning = await learning_loop(rows)
    after = hashlib.sha256(REGISTRY.read_bytes()).hexdigest()
    metrics = {
        "heldout_recall": scores["recall"],
        "heldout_fpr": scores["fpr"],
        "diagnosis_accuracy": ok / n,
        "bad_candidates_rejected": rejected / len(BAD),
        "registry_unchanged_by_agents": float(before == after),
        "episodes_only_after_review": float(early == 0),
        **learning,
        **{f"recall_{k}": v for k, v in scores["per_fault_recall"].items()},
    }
    return gate("wind-turbine-continual-learning", metrics, THRESHOLDS, rows)


async def learning_loop(rows: list[dict]) -> dict:
    """memory -> evals -> learning -> gating -> improve, against temporary lesson registries."""
    scen = json.loads((DATA / "learning_scenarios.json").read_text())
    cases = json.loads((HERE / "gold" / "lesson_eval.json").read_text())
    with tempfile.TemporaryDirectory() as tmp:
        lessons_path = Path(tmp) / "lessons.json"
        desk = DiagnosticsDesk(lessons=LessonRegistry(lessons_path))
        w = scen["sensor_drift_B"]
        desk.publish(w["rows"])
        res = await desk.check(w["turbine_id"])
        out = (
            await desk.decide(
                res.run_id,
                res.request_id,
                Decision(
                    False,
                    "eval-tech",
                    "gearbox fine, sensor reads high",
                    overrides={"confirmed_diagnosis": "sensor_drift"},
                ),
            )
        ).output
        cand = out["lesson_candidate"]
        fresh = DiagnosticsDesk(lessons=LessonRegistry(lessons_path))  # gate replays on seed memory only
        base = baseline_case_fn(fresh.detector[0], fresh.episodes)
        broad = {"lesson_id": "LS-broad", "when": {"high": ["gearbox_residual_c"]}, "then": "sensor_drift"}
        r_broad = promote_lesson(broad, "eval-gate", base, Path(tmp) / "broad.json", cases)
        rec = promote_lesson(cand, "eval-gate", base, lessons_path, cases) if cand else {"decision": "none"}
        rows += [
            {"kind": "lesson", "lesson": cand, "gate": rec},
            {"kind": "lesson", "lesson": broad, "gate": r_broad},
        ]
        promoted = LessonRegistry(lessons_path).promoted()
        applied_ok, applied_n = 0, 0
        for c in cases:
            _b, ctx, sig = base(c)
            for lesson in promoted:
                if applies(lesson, ctx, sig)[0]:
                    applied_n += 1
                    applied_ok += c["label"] == lesson["then"]
        after = DiagnosticsDesk(lessons=LessonRegistry(lessons_path))
        safer = []
        for key, expect in (("sensor_drift_B", "sensor_drift"), ("sensor_drift_on_A", "gearbox_bearing")):
            after.publish(scen[key]["rows"])
            r = await after.check(scen[key]["turbine_id"])
            safer.append(r.pending is not None and r.pending.diagnosis == expect)
            rows.append(
                {
                    "kind": "after_learning",
                    "case": key,
                    "diagnosis": r.pending and r.pending.diagnosis,
                    "gating": r.pending and r.pending.gating,
                }
            )
    return {
        "lesson_learned_from_feedback": float(rec["decision"] == "promoted"),
        "overbroad_lesson_rejected": float(r_broad["decision"] == "rejected"),
        "lesson_accuracy_before": rec.get("accuracy_before", 0.0),
        "lesson_accuracy_after": rec.get("accuracy_after", 0.0),
        "lesson_gain": round(rec.get("accuracy_after", 0.0) - rec.get("accuracy_before", 0.0), 4),
        "gating_precision": applied_ok / applied_n if applied_n else 0.0,
        "safer_decision_after_learning": float(all(safer)),
    }


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
