"""Coordinator workflow end to end."""

import importlib.util
import json
from pathlib import Path

import pytest
from agent_framework import ChatResponse, Message

from labcore.foundry import MockFoundryChatClient
from labcore.hitl import Decision
from labcore.infra_check import build, find_bicep
from roadgraph.card import CARD
from roadgraph.service import PlanningDesk

LAB = Path(__file__).resolve().parents[1]


async def test_coordinator_dispatches_every_worker_then_pauses():
    desk = PlanningDesk()
    res = await desk.plan(400_000)
    p = res.pending
    assert p.plan["total_cost_usd"] <= 400_000 and p.plan["items"]
    assert p.narrative["segment_ids"] == [i["segment_id"] for i in p.plan["items"]]
    assert res.runtime["guard"].worker_calls == 4


async def test_engineer_can_trim_plan_and_no_work_orders_issued():
    desk = PlanningDesk()
    res = await desk.plan(400_000)
    first = res.pending.plan["items"][0]["segment_id"]
    out = (
        await desk.decide(
            res.run_id, res.request_id, Decision(True, "eng-rossi", overrides={"remove_segments": [first]})
        )
    ).output
    assert first not in [i["segment_id"] for i in out["maintenance_plan"]]
    assert out["work_orders_issued"] is False
    assert out["trail"][:8] == [
        "planning_coordinator",
        "graph_engineering",
        "planning_coordinator",
        "graph_features",
        "planning_coordinator",
        "maintenance_priority",
        "planning_coordinator",
        "closure_impact",
    ]
    assert out["road_health_report"]["mean_pci"] > 0 and out["closure_impacts"]


async def test_returned_plan_has_no_items():
    desk = PlanningDesk()
    res = await desk.plan(200_000)
    out = (
        await desk.decide(res.run_id, res.request_id, Decision(False, "eng-rossi", "recheck costs"))
    ).output
    assert out["status"] == "returned_for_rework" and out["maintenance_plan"] == []


async def test_what_if_closure_is_simulated_and_reported():
    desk = PlanningDesk()
    res = await desk.plan(100_000, what_if=["w-E1-E2"])
    out = (await desk.decide(res.run_id, res.request_id, Decision(True, "eng-rossi"))).output
    imp = out["closure_impacts"]["w-E1-E2"]
    assert imp["hospital_access_lost"] and imp["stranded_trips"] > 0


async def test_existing_closure_is_respected():
    desk = PlanningDesk()
    res = await desk.plan(400_000, closed_segments=["w-W13-E0"])
    ids = [r["segment_id"] for r in res.pending.top_ranked]
    assert "w-W13-E0" not in ids
    south = next(r for r in res.pending.top_ranked if r["segment_id"] == "w-W33-E3")
    assert (
        south["criticality"] > 0.5
    )  # with the north bridge shut, the south bridge carries the hospital route


async def test_narrative_with_wrong_total_is_replaced_by_draft():
    def wrong(_m, opts):
        if opts.get("response_format") is not None:
            txt = json.dumps({"title": "t", "narrative": "n", "segment_ids": [], "total_cost_usd": 1})
            return ChatResponse(messages=[Message(role="assistant", contents=[txt])])
        return None

    desk = PlanningDesk(writer_client=MockFoundryChatClient(script=wrong))
    res = await desk.plan(400_000)
    assert res.pending.narrative["total_cost_usd"] == res.pending.plan["total_cost_usd"]
    assert res.pending.issues


def _eval():
    spec = importlib.util.spec_from_file_location("road_eval", LAB / "evals" / "run_eval.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


async def test_eval_gate_passes():
    rep = await _eval().evaluate()
    assert rep.passed, rep.failures


async def test_pothole_only_priority_fails_the_gate(monkeypatch):
    from roadgraph import graph_ops

    orig = graph_ops.priority

    def pothole_greedy(g, feats):
        rows = orig(g, feats)
        return sorted(rows, key=lambda r: -r["potholes"])

    monkeypatch.setattr(graph_ops, "priority", pothole_greedy)
    rep = await _eval().evaluate()
    assert rep.metrics["pairwise_order_accuracy"] < 1.0 and not rep.passed


def test_agent_card_current():
    path = LAB.parents[1] / "control-plane" / "agent-cards" / "road-network-maintenance-graph.json"
    assert json.loads(path.read_text()) == CARD


@pytest.mark.skipif(find_bicep() is None, reason="bicep CLI not installed")
def test_bicep_compiles():
    res = build(LAB / "infra" / "main.bicep")
    assert res.returncode == 0, res.stderr
