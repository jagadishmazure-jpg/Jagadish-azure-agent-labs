import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
from agent_framework import Agent, tool

from labcore.foundry import MockFoundryChatClient
from labcore.hitl import Decision
from labcore.infra_check import build, find_bicep
from labcore.middleware import deny_tools
from turbine_cl import DATA, REGISTRY
from turbine_cl.card import CARD
from turbine_cl.diagnose import DENIED
from turbine_cl.service import DiagnosticsDesk

LAB = Path(__file__).resolve().parents[1]
SCEN = json.loads((DATA / "stream_scenarios.json").read_text())


async def run(name: str, desk: DiagnosticsDesk | None = None):
    desk = desk or DiagnosticsDesk()
    desk.publish(SCEN[name]["rows"])
    return desk, await desk.check("WTG-07")


async def test_normal_window_stops_after_detection():
    _, res = await run("normal")
    assert res.pending is None and res.output["status"] == "no_anomaly" and not res.output["episode_written"]


async def test_fault_window_reaches_technician_with_catalog_actions():
    _, res = await run("gearbox_bearing")
    p = res.pending
    assert p.diagnosis == "gearbox_bearing" and p.recommendation["urgency"] == "within 24h"
    assert "borescope_gearbox" in p.recommendation["actions"]
    assert set(p.recommendation["cited_episodes"]) <= {s["episode_id"] for s in p.similar}


async def test_confirmed_episode_is_written_and_then_retrieved():
    desk, res = await run("icing")
    out = (await desk.decide(res.run_id, res.request_id, Decision(True, "tech-lee", "heaters on"))).output
    assert out["episode_written"] and out["episode"]["confirmed_by"] == "tech-lee"
    desk.publish([{**r, "t": r["t"] + 100} for r in SCEN["icing"]["rows"]])
    again = await desk.check("WTG-07")
    assert out["episode"]["episode_id"] in {s["episode_id"] for s in again.pending.similar}


async def test_rejection_writes_false_alarm_episode():
    desk, res = await run("generator_overheat")
    out = (await desk.decide(res.run_id, res.request_id, Decision(False, "tech-lee", "sensor fault"))).output
    assert out["status"] == "closed_false_alarm" and out["episode"]["diagnosis"] == "false_alarm"


async def test_workflow_never_retrains_or_touches_registry(monkeypatch):
    before = hashlib.sha256(REGISTRY.read_bytes()).hexdigest()
    desk = DiagnosticsDesk()
    from turbine_cl import detector

    def boom(*a, **k):
        raise AssertionError("fit called during a workflow run")

    monkeypatch.setattr(detector.IsolationForestDetector, "fit", boom)
    monkeypatch.setattr(detector.ZScoreDetector, "fit", boom)
    for name in SCEN:
        desk, res = await run(name, desk)
        if res.pending:
            await desk.decide(res.run_id, res.request_id, Decision(True, "t"))
    assert hashlib.sha256(REGISTRY.read_bytes()).hexdigest() == before


def test_promotion_is_not_reachable_from_the_workflow():
    src = (LAB / "src" / "turbine_cl" / "workflow.py").read_text() + (
        LAB / "src" / "turbine_cl" / "service.py"
    ).read_text()
    assert "turbine_cl.promotion" not in src and "promote(" not in src and ".fit(" not in src


async def test_promote_tool_is_deny_listed_for_agents():
    called = []

    @tool
    def promote_detector(query: str) -> str:
        """Would promote a detector."""
        called.append(query)
        return "promoted"

    agent = Agent(client=MockFoundryChatClient(), tools=[promote_detector], middleware=[deny_tools(DENIED)])
    assert "DENIED" in (await agent.run("promote v2")).text and called == []


async def test_short_window_is_insufficient_data():
    desk = DiagnosticsDesk()
    desk.publish(SCEN["normal"]["rows"][:2])
    res = await desk.check("WTG-07")
    assert res.output["status"] == "insufficient_data"


def _eval():
    spec = importlib.util.spec_from_file_location("wtg_eval", LAB / "evals" / "run_eval.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


async def test_eval_gate_passes():
    rep = await _eval().evaluate()
    assert rep.passed, rep.failures


def test_agent_card_current():
    path = LAB.parents[1] / "control-plane" / "agent-cards" / "wind-turbine-continual-learning.json"
    assert json.loads(path.read_text()) == CARD


@pytest.mark.skipif(find_bicep() is None, reason="bicep CLI not installed")
def test_bicep_compiles():
    res = build(LAB / "infra" / "main.bicep")
    assert res.returncode == 0, res.stderr
