"""Eval-gated detector promotion. A person runs this; it is not an agent tool and nothing in the
workflow imports it.

    python -m turbine_cl.promotion --version iforest-v2 --n-estimators 200 --contamination 0.03 \
        --approved-by "jane.doe (reliability engineer)" [--registry models/registry.json] [--dry-run]

Steps: train the candidate on the registered training data -> score it and the champion on the
held-out failure / normal windows -> promote only if the candidate passes the absolute gate AND is
not worse than the champion on recall, with a named approver. Every attempt is appended to the
registry's audit log, including rejections."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from turbine_cl import DATA, LAB_ROOT, REGISTRY
from turbine_cl.detector import DetectorRegistry, data_hash, make_detector, score_window, train_rows
from turbine_cl.features import matrix

HELDOUT = LAB_ROOT / "evals" / "gold" / "heldout.json"
MIN_RECALL = 0.9
MAX_FPR = 0.1


def evaluate_detector(det, windows: list[dict] | None = None) -> dict:
    windows = windows or json.loads(HELDOUT.read_text())
    fails = [w for w in windows if w["label"] != "normal"]
    normals = [w for w in windows if w["label"] == "normal"]
    tp = sum(score_window(det, w["rows"]).anomalous for w in fails)
    fp = sum(score_window(det, w["rows"]).anomalous for w in normals)
    per_fault: dict[str, list[int]] = {}
    for w in fails:
        per_fault.setdefault(w["label"], []).append(int(score_window(det, w["rows"]).anomalous))
    return {
        "recall": tp / len(fails),
        "fpr": fp / len(normals),
        "per_fault_recall": {k: sum(v) / len(v) for k, v in sorted(per_fault.items())},
    }


def promote(
    version: str, params: dict, approved_by: str, registry_path: Path = REGISTRY, dry_run: bool = False
) -> dict:
    if not approved_by.strip():
        raise ValueError("promotion needs a named approver")
    reg_obj = DetectorRegistry(registry_path)
    reg = reg_obj.read()
    champ_det, champ = reg_obj.load_champion()
    training = champ["training_data"]
    cand = make_detector(params).fit(matrix(train_rows(training)))
    c_scores, ch_scores = evaluate_detector(cand), evaluate_detector(champ_det)
    reasons = []
    if c_scores["recall"] < MIN_RECALL:
        reasons.append(f"recall {c_scores['recall']:.2f} < {MIN_RECALL}")
    if c_scores["fpr"] > MAX_FPR:
        reasons.append(f"false-positive rate {c_scores['fpr']:.2f} > {MAX_FPR}")
    if c_scores["recall"] < ch_scores["recall"]:
        reasons.append("recall below champion")
    decision = "promoted" if not reasons else "rejected"
    record = {
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "candidate": version,
        "approved_by": approved_by,
        "decision": decision,
        "reasons": reasons,
        "candidate_scores": c_scores,
        "champion_scores": ch_scores,
        "previous_champion": reg["champion"],
        "dry_run": dry_run,
    }
    if not dry_run:
        reg["audit"].append(record)
        if decision == "promoted":
            reg["versions"].append(
                {
                    "version": version,
                    "params": params,
                    "training_data": training,
                    "training_data_hash": data_hash(DATA / training),
                    "scores": c_scores,
                    "registered_by": approved_by,
                }
            )
            reg["champion"] = version
        registry_path.write_text(json.dumps(reg, indent=2) + "\n")
    return record


def bootstrap(registry_path: Path = REGISTRY) -> dict:
    """Create the initial registry (champion iforest-v1). Used once to produce models/registry.json."""
    params = {"kind": "isolation_forest", "n_estimators": 100, "contamination": 0.02, "random_state": 7}
    det = make_detector(params).fit(matrix(train_rows("normal_train.json")))
    reg = {
        "champion": "iforest-v1",
        "versions": [
            {
                "version": "iforest-v1",
                "params": params,
                "training_data": "normal_train.json",
                "training_data_hash": data_hash(DATA / "normal_train.json"),
                "scores": evaluate_detector(det),
                "registered_by": "initial registration",
            }
        ],
        "audit": [],
    }
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps(reg, indent=2) + "\n")
    return reg


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version")
    ap.add_argument("--n-estimators", type=int, default=100)
    ap.add_argument("--contamination", type=float, default=0.02)
    ap.add_argument("--random-state", type=int, default=7)
    ap.add_argument("--approved-by", default="")
    ap.add_argument("--registry", type=Path, default=REGISTRY)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--bootstrap", action="store_true")
    a = ap.parse_args(argv)
    if a.bootstrap:
        print(json.dumps(bootstrap(a.registry)["versions"][0]["scores"], indent=2))
        return 0
    params = {
        "kind": "isolation_forest",
        "n_estimators": a.n_estimators,
        "contamination": a.contamination,
        "random_state": a.random_state,
    }
    rec = promote(a.version, params, a.approved_by, a.registry, a.dry_run)
    print(json.dumps(rec, indent=2))
    return 0 if rec["decision"] == "promoted" else 1


if __name__ == "__main__":
    sys.exit(main())
