"""Learned lessons: memory is not learning.

* `LessonRegistry` holds PROMOTED lessons (models/lessons.json). Agents read it; they never write it.
* `ContextGate.applies(lesson, context, signature)` decides whether a promoted lesson fits the case.
* `promote_lesson()` is the eval gate a person runs: replay the candidate on the lesson eval set and
  promote only if it fixes at least one case, breaks none, and does not lower accuracy."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from turbine_cl import LAB_ROOT
from turbine_cl.features import FEATURES

LESSONS = LAB_ROOT / "models" / "lessons.json"
LESSON_EVAL = LAB_ROOT / "evals" / "gold" / "lesson_eval.json"


def read(path: Path = LESSONS) -> dict:
    return json.loads(path.read_text()) if path.exists() else {"promoted": [], "audit": []}


class LessonRegistry:
    def __init__(self, path: Path = LESSONS) -> None:
        self.path = path

    def promoted(self) -> list[dict]:
        return list(read(self.path)["promoted"])


def applies(lesson: dict, context: dict, signature: list[float]) -> tuple[bool, str]:
    cond = lesson["when"]
    if "turbine_model" in cond and context.get("turbine_model") != cond["turbine_model"]:
        return False, f"turbine model {context.get('turbine_model')} != {cond['turbine_model']}"
    if "max_ambient_c" in cond and context.get("ambient_c", 99) > cond["max_ambient_c"]:
        return False, "ambient too warm"
    z = dict(zip(FEATURES, signature, strict=True))
    for f in cond.get("high", []):
        if z[f] < 3.0:
            return False, f"{f} not elevated"
    for f in cond.get("normal", []):
        if abs(z[f]) >= 1.5:
            return False, f"{f} not normal"
    return True, "context and pattern match"


def replay(lesson: dict | None, rows_to_case, cases: list[dict]) -> list[dict]:
    """rows_to_case(case) -> (baseline_diagnosis, context, signature)."""
    out = []
    for c in cases:
        base, ctx, sig = rows_to_case(c)
        pred = base
        if lesson is not None and applies(lesson, ctx, sig)[0]:
            pred = lesson["then"]
        out.append(
            {"turbine_id": c["turbine_id"], "label": c["label"], "baseline": base, "with_lesson": pred}
        )
    return out


def promote_lesson(
    candidate: dict, approved_by: str, rows_to_case, path: Path = LESSONS, cases: list[dict] | None = None
) -> dict:
    if not approved_by.strip():
        raise ValueError("lesson promotion needs a named approver")
    cases = cases if cases is not None else json.loads(LESSON_EVAL.read_text())
    res = replay(candidate, rows_to_case, cases)
    before = sum(r["baseline"] == r["label"] for r in res)
    after = sum(r["with_lesson"] == r["label"] for r in res)
    broken = [r for r in res if r["baseline"] == r["label"] and r["with_lesson"] != r["label"]]
    fixed = [r for r in res if r["baseline"] != r["label"] and r["with_lesson"] == r["label"]]
    reasons = []
    if not fixed:
        reasons.append("fixes no held-out case")
    if broken:
        reasons.append(f"breaks {len(broken)} case(s) that were right before")
    if after < before:
        reasons.append("accuracy drops")
    decision = "promoted" if not reasons else "rejected"
    reg = read(path)
    rec = {
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "lesson_id": candidate["lesson_id"],
        "approved_by": approved_by,
        "decision": decision,
        "reasons": reasons,
        "accuracy_before": before / len(res),
        "accuracy_after": after / len(res),
        "fixed": len(fixed),
        "broken": len(broken),
    }
    reg["audit"].append(rec)
    if decision == "promoted":
        reg["promoted"].append({**candidate, "promoted_by": approved_by})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(reg, indent=2) + "\n")
    return rec


if __name__ == "__main__":  # pragma: no cover
    print(json.dumps(read(), indent=2))
    sys.exit(0)
