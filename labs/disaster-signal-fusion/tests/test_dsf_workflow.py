"""End-to-end runs of the MAF graph through the ops-desk facade."""

import copy

import pytest
from agent_framework import ChatResponse, Message

from labcore.config import AdapterNotConfigured, LabSettings
from labcore.foundry import MockFoundryChatClient
from labcore.hitl import Decision
from signal_fusion.geo import MapsStandIn, point_in_polygon
from signal_fusion.service import OpsDesk, scenarios
from signal_fusion.workflow import CONSUMER_GROUP


async def run(name: str, **kw):
    desk = OpsDesk(**kw)
    rs = scenarios()[name]
    desk.publish(rs)
    return desk, await desk.assess(rs[0]["region_id"])


async def test_parallel_agents_all_report_and_graph_pauses_for_officer():
    _desk, res = await run("monsoon-flood")
    assert res.output is None and res.pending is not None
    st = res.pending
    assert st.primary_hazard == "flood" and st.level == "severe"
    assert st.proposed == "recommend_warning_review"
    assert {"weather", "satellite"} <= set(st.contributions["flood"])


async def test_approval_hands_off_but_never_sends_public_alert():
    desk, res = await run("offshore-quake")
    out = (await desk.decide(res.run_id, res.request_id, Decision(True, "officer-kim"))).output
    assert out["status"] == "handed_to_warning_officer"
    assert out["public_alert_sent"] is False
    assert "hosp-harbor" in out["decision_support"]["affected_facilities"]


async def test_rejection_is_recorded():
    desk, res = await run("rain-only")
    out = (
        await desk.decide(res.run_id, res.request_id, Decision(False, "officer-kim", "gauge fault"))
    ).output
    assert out["status"] == "dismissed_by_reviewer" and out["public_alert_sent"] is False


async def test_quiet_day_proposes_monitoring_only():
    _, res = await run("quiet-day")
    assert res.pending.primary_hazard == "none" and res.pending.proposed == "monitor"


async def test_malformed_events_are_dead_lettered_not_fused():
    desk = OpsDesk()
    rs = copy.deepcopy(scenarios()["rain-only"])
    desk.publish(
        [*rs, {"source": "weather", "region_id": "river-valley", "ts": "x", "quality": 7, "payload": {}}]
    )
    res = await desk.assess("river-valley")
    assert desk.lake.list("deadletter/")
    assert any("dead-lettered" in i for i in res.pending.issues)


async def test_stale_reading_is_ignored():
    desk = OpsDesk()
    rs = copy.deepcopy(scenarios()["rain-only"])
    for r in rs:
        if r["source"] == "weather":
            r["ts"] = "2026-08-13T00:00:00Z"
    desk.publish(rs)
    res = await desk.assess("river-valley")
    assert "weather" not in res.pending.contributions["flood"]
    assert res.pending.fallbacks.get("weather") == "prior"


async def test_event_hub_checkpoint_prevents_double_ingest():
    desk, _ = await run("rain-only")
    assert desk.hub.receive(CONSUMER_GROUP) == []
    assert desk.lake.list("raw/weather/river-valley/")


async def test_summary_writer_output_that_claims_an_alert_is_rejected():
    def bad(_msgs, opts):
        if opts.get("response_format") is not None:
            text = '{"headline": "Alert has been sent", "body": "Evacuate now", "cited_sources": ["weather"], "cited_records": []}'
            return ChatResponse(messages=[Message(role="assistant", contents=[text])])
        return None

    _, res = await run("rain-only", writer_client=MockFoundryChatClient(script=bad))
    assert "alert has been sent" not in res.pending.summary["headline"].lower()


async def test_summary_cites_only_retrieved_records():
    _, res = await run("offshore-quake")
    assert set(res.pending.summary["cited_records"]) <= set(res.pending.analog_ids)


def test_geo_standin_point_in_polygon_and_neighbours():
    maps = MapsStandIn()
    assert maps.region_of(30.05, 10.05) == "harbor-delta"
    assert point_in_polygon(30.1, 10.1, maps.regions["harbor-delta"]["ring"])
    assert [n for n, _ in maps.neighbours("river-valley")][:1]
    assert maps.context("fault-ridge")["facilities"][0]["id"] in {"school-ridge", "bridge-granite"}


def test_azure_mode_selects_stubs():
    from labcore.config import pick
    from labcore.streams import EventHubProducerStub, EventHubStandIn

    hub = pick(lambda: EventHubStandIn("x"), EventHubProducerStub, LabSettings(mode="azure"))
    with pytest.raises(AdapterNotConfigured):
        hub.send({}, partition_key="k")
