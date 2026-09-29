"""Memory is not learning: evaluation -> learning signal -> candidate lesson -> lesson gate -> context gating."""

import json

import pytest

from labcore.hitl import Decision
from turbine_cl import DATA, LAB_ROOT
from turbine_cl.agents import (
    ContinualLearningAgent,
    EvaluationAgent,
    LearningSignalsAgent,
    StaticMaintenanceAgent,
    baseline_case_fn,
)
from turbine_cl.lessons import LESSONS, LessonRegistry, applies, promote_lesson
from turbine_cl.service import DiagnosticsDesk

SCEN = json.loads((DATA / "learning_scenarios.json").read_text())
CASES = json.loads((LAB_ROOT / "evals" / "gold" / "lesson_eval.json").read_text())


async def _correct_drift(desk):
    w = SCEN["sensor_drift_B"]
    desk.publish(w["rows"])
    res = await desk.check(w["turbine_id"])
    assert res.pending.diagnosis == "gearbox_bearing"  # memory + patterns get it wrong at first
    assert res.pending.context["turbine_model"].startswith("model-B")
    assert not res.pending.evaluation["checks"][
        "not_repeating_failed_work"
    ]  # borescope found nothing last month
    d = Decision(False, "tech-lee", "sensor reads high", overrides={"confirmed_diagnosis": "sensor_drift"})
    return (await desk.decide(res.run_id, res.request_id, d)).output


async def test_correction_becomes_signal_and_candidate_not_promotion(tmp_path):
    desk = DiagnosticsDesk(lessons=LessonRegistry(tmp_path / "l.json"))
    out = await _correct_drift(desk)
    assert out["status"] == "corrected" and out["learning_signal"]["kind"] == "wrong_diagnosis"
    cand = out["lesson_candidate"]
    assert cand["status"] == "candidate" and cand["when"]["turbine_model"].startswith("model-B")
    assert "vibration_residual" in cand["when"]["normal"]
    assert not (tmp_path / "l.json").exists()  # the workflow never promotes
    assert out["trail"][-3:] == ["technician_review", "learning_signals", "continual_learning"]


async def test_lesson_gate_promotes_specific_and_rejects_broad(tmp_path):
    desk = DiagnosticsDesk(lessons=LessonRegistry(tmp_path / "l.json"))
    cand = (await _correct_drift(desk))["lesson_candidate"]
    fresh = DiagnosticsDesk()
    base = baseline_case_fn(fresh.detector[0], fresh.episodes)
    ok = promote_lesson(cand, "lead-eng", base, tmp_path / "l.json", CASES)
    assert ok["decision"] == "promoted" and ok["broken"] == 0 and ok["accuracy_after"] > ok["accuracy_before"]
    broad = {"lesson_id": "x", "when": {"high": ["gearbox_residual_c"]}, "then": "sensor_drift"}
    bad = promote_lesson(broad, "lead-eng", base, tmp_path / "b.json", CASES)
    assert bad["decision"] == "rejected" and bad["broken"] > 0
    with pytest.raises(ValueError):
        promote_lesson(cand, " ", base, tmp_path / "c.json", CASES)


async def test_context_gating_prevents_negative_transfer(tmp_path):
    path = tmp_path / "l.json"
    lesson = {
        "lesson_id": "LS-1",
        "then": "sensor_drift",
        "when": {
            "turbine_model": "model-B-2.3MW-cold",
            "high": ["gearbox_residual_c"],
            "normal": ["vibration_residual"],
        },
    }
    path.write_text(json.dumps({"promoted": [lesson], "audit": []}))
    desk = DiagnosticsDesk(lessons=LessonRegistry(path))
    got = {}
    for key in ("sensor_drift_B", "sensor_drift_on_A"):
        desk.publish(SCEN[key]["rows"])
        p = (await desk.check(SCEN[key]["turbine_id"])).pending
        got[key] = (p.diagnosis, p.gating["lesson_applied"])
    assert got["sensor_drift_B"] == ("sensor_drift", "LS-1")
    assert got["sensor_drift_on_A"] == ("gearbox_bearing", None)


def test_real_bearing_on_model_b_is_not_gated_into_drift():
    lesson = {
        "when": {
            "turbine_model": "model-B-2.3MW-cold",
            "high": ["gearbox_residual_c"],
            "normal": ["vibration_residual"],
        },
        "then": "sensor_drift",
    }
    desk = DiagnosticsDesk()
    base = baseline_case_fn(desk.detector[0], desk.episodes)
    real = [c for c in CASES if c["label"] == "gearbox_bearing" and c["turbine_model"].startswith("model-B")]
    assert real and not any(applies(lesson, *base(c)[1:])[0] for c in real)


def test_static_agent_explains_anomaly_with_feature_contributions():
    desk = DiagnosticsDesk()
    s = StaticMaintenanceAgent(desk.detector[0]).run(SCEN["sensor_drift_B"]["rows"])
    c = s["contributions"]
    assert c["method"] in {"ablation", "shap_kernel"} and c["features"][0]["feature"] == "gearbox_residual_c"
    assert c["score"] > c["baseline_score"]


def test_evaluation_and_signal_agents():
    ev = EvaluationAgent()
    ctx = {"recent_work": [], "turbine_model": "m", "ambient_c": 5.0, "wind_ms": 9.0}
    pre = ev.pre(
        {"pattern": "icing"},
        {"memory_diagnosis": "icing", "memory_confidence": 0.9},
        "icing",
        ["enable_blade_heating"],
        ctx,
    )
    assert pre["passed"] and pre["confidence"] == 0.9
    post = ev.post("icing", "icing", True)
    assert LearningSignalsAgent().run(post, pre, ctx, [0.0] * 7) is None  # nothing to learn from a clean win
    assert ContinualLearningAgent().run(None, []) is None


def test_repo_lesson_registry_has_no_promoted_lessons_from_tests():
    assert json.loads(LESSONS.read_text())["promoted"] == []
