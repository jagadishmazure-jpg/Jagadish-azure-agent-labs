"""The six agents of the lab, in flow order: memory -> evals -> learning -> gating -> improve.

1. StaticMaintenanceAgent   Isolation Forest (registered champion) + physics-residual pattern rules
2. EpisodicMemoryAgent      similar past incidents from the episode store
3. ContextGatingAgent       applies a PROMOTED lesson only when turbine model / weather / pattern fit
4. EvaluationAgent          checks diagnosis + action quality before the technician, correctness after
5. LearningSignalsAgent     turns a wrong or doubtful decision into a structured feedback record
6. ContinualLearningAgent   distils feedback into a candidate lesson (never promotes it itself)"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from labcore.explain import contributions
from turbine_cl import diagnose as dx
from turbine_cl.detector import score_window
from turbine_cl.episodes import EpisodeStore
from turbine_cl.features import FEATURES
from turbine_cl.lessons import LessonRegistry, applies


def z_of(signature: list[float]) -> dict[str, float]:
    return dict(zip(FEATURES, signature, strict=True))


@dataclass
class StaticMaintenanceAgent:
    detector: object

    PATTERNS = (  # (label, rule on z-scores)
        ("pitch_fault", lambda z: z["pitch_residual_deg"] > 3 and z["power_residual_pct"] < -3),
        ("generator_overheat", lambda z: z["generator_residual_c"] > 3),
        ("icing", lambda z: z["power_residual_pct"] < -3 and z["ambient_c"] < -1),
        ("gearbox_bearing", lambda z: z["gearbox_residual_c"] > 3),
    )

    def run(self, rows: list[dict]) -> dict:
        r = score_window(self.detector, rows)
        z = z_of(r.signature)
        pattern = next((lab for lab, rule in self.PATTERNS if rule(z)), "unknown_pattern")
        return {
            "anomalous": r.anomalous,
            "flagged_rows": r.flagged_rows,
            "signature": r.signature,
            "top_features": r.top_features,
            "pattern": pattern,
            "contributions": self.explain(r.signature),
        }

    def explain(self, signature: list[float]) -> dict:
        """Which residual features pushed the anomaly score up (baseline = healthy mean, z = 0)."""
        det = self.detector
        if getattr(det, "model", None) is not None:

            def f(z):
                return float(-det.model.score_samples(np.asarray(z)[None, :])[0])
        else:

            def f(z):
                return float(np.abs(np.asarray(z)[:-1]).max())

        return contributions(f, signature, [0.0] * len(FEATURES), FEATURES)


@dataclass
class EpisodicMemoryAgent:
    store: EpisodeStore

    def run(self, signature: list[float], context: dict, static_pattern: str) -> dict:
        hits = self.store.similar(signature)
        model = context.get("turbine_model")
        # an episode confirmed on another turbine model is not evidence for this one
        similar = [h for h in hits if h.get("turbine_model") in (None, model)][:3]
        excluded = [h["episode_id"] for h in hits if h.get("turbine_model") not in (None, model)]
        label, conf = dx.diagnose(similar)
        source = "memory"
        if label == "unknown_pattern" and static_pattern != "unknown_pattern":
            label, conf, source = static_pattern, 0.5, "static_pattern"  # nothing similar enough: fall back
        return {
            "similar": similar,
            "excluded_other_model": excluded,
            "memory_diagnosis": label,
            "memory_confidence": conf,
            "source": source,
        }


@dataclass
class ContextGatingAgent:
    registry: LessonRegistry = field(default_factory=LessonRegistry)

    def run(self, baseline: str, context: dict, signature: list[float]) -> dict:
        decisions = []
        for lesson in self.registry.promoted():
            ok, why = applies(lesson, context, signature)
            decisions.append({"lesson_id": lesson["lesson_id"], "applied": ok, "why": why})
            if ok:
                return {
                    "diagnosis": lesson["then"],
                    "lesson_applied": lesson["lesson_id"],
                    "gating": decisions,
                }
        return {"diagnosis": baseline, "lesson_applied": None, "gating": decisions}


class EvaluationAgent:
    def pre(self, static: dict, memory: dict, diagnosis: str, actions: list[str], context: dict) -> dict:
        checks = {
            "static_and_memory_agree": static["pattern"] == memory["memory_diagnosis"],
            "actions_in_catalog": set(actions) <= set(dx.CATALOG.get(diagnosis, [])),
            "urgent_has_derate": diagnosis not in dx.URGENT or "derate_to_70pct" in actions,
            "not_repeating_failed_work": not any(
                h["action"] in actions and h["result"] in {"no damage found", "normal"}
                for h in context["recent_work"]
            ),
        }
        conf = memory["memory_confidence"] * (1.0 if checks["static_and_memory_agree"] else 0.6)
        conf *= 0.7 if not checks["not_repeating_failed_work"] else 1.0
        return {"checks": checks, "confidence": round(conf, 3), "passed": all(checks.values())}

    def post(self, diagnosis: str, confirmed: str, approved: bool) -> dict:
        return {
            "diagnosis_correct": approved and confirmed == diagnosis,
            "confirmed": confirmed,
            "proposed": diagnosis,
        }


class LearningSignalsAgent:
    def run(self, post: dict, pre: dict, context: dict, signature: list[float]) -> dict | None:
        if post["diagnosis_correct"] and pre["passed"]:
            return None
        kind = "wrong_diagnosis" if not post["diagnosis_correct"] else "weak_decision"
        return {
            "kind": kind,
            "proposed": post["proposed"],
            "confirmed": post["confirmed"],
            "failed_checks": [k for k, v in pre["checks"].items() if not v],
            "context": {k: context[k] for k in ("turbine_model", "ambient_c", "wind_ms")},
            "signature": signature,
        }


class ContinualLearningAgent:
    """Distils a feedback record into a candidate lesson: when <model, strongly deviating features,
    features that stayed normal> then <confirmed diagnosis>. Candidates wait for the lesson gate."""

    def run(self, signal: dict | None, candidates: list[dict]) -> dict | None:
        if not signal or signal["kind"] != "wrong_diagnosis" or signal["confirmed"] == "false_alarm":
            return None
        z = z_of(signal["signature"])
        high = [f for f in FEATURES[:-1] if z[f] >= 3.0]
        normal = [
            f for f in ("vibration_residual", "power_residual_pct", "generator_residual_c") if abs(z[f]) < 1.5
        ]
        cand = {
            "lesson_id": f"LS-{len(candidates) + 1:03d}-{signal['confirmed']}",
            "when": {"turbine_model": signal["context"]["turbine_model"], "high": high, "normal": normal},
            "then": signal["confirmed"],
            "learned_from": signal["proposed"],
            "status": "candidate",
        }
        candidates.append(cand)
        return cand


def baseline_case_fn(detector, store: EpisodeStore):
    """Replay helper for the lesson gate: what would static + memory (no lessons) say for a case?"""
    from turbine_cl.context import turbine_context

    static_agent, memory_agent = StaticMaintenanceAgent(detector), EpisodicMemoryAgent(store)

    def run(case: dict) -> tuple[str, dict, list[float]]:
        s = static_agent.run(case["rows"])
        ctx = turbine_context(case["turbine_id"], case["rows"])
        m = memory_agent.run(s["signature"], ctx, s["pattern"])
        return m["memory_diagnosis"], ctx, s["signature"]

    return run
