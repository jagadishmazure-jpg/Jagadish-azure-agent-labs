"""The MAF workflow.

    ingest_watch ──┬─> seismic_analysis ──────┐
                   ├─> satellite_monitoring ──┼─> join ─> historical_pattern ─> prediction_coordinator
                   └─> weather_correlation ───┘                                        │
                                              alert_decision (HITL request_info) <─ situation_summary
                                                  └─> output (never a public alert)

Shared run state lives in workflow state (`ctx.set_state("desk", ...)`); the three parallel agents
return `Finding` packets that the join collects."""

from __future__ import annotations

from dataclasses import asdict

from agent_framework import Workflow, WorkflowBuilder, WorkflowContext, handler, response_handler
from pydantic import ValidationError

from labcore.hitl import Decision
from labcore.streams import DataLakeStandIn, EventHubStandIn
from labcore.workflow import LabNode
from signal_fusion import risk as risk_mod
from signal_fusion import summary as summary_mod
from signal_fusion.agents import (
    HistoricalPatternAgent,
    PredictionCoordinator,
    SatelliteMonitoringAgent,
    SeismicAnalysisAgent,
    WeatherCorrelationAgent,
)
from signal_fusion.functions import FUNCTIONS, Rejected, hours_between
from signal_fusion.geo import MapsStandIn
from signal_fusion.models import SOURCES, AlertReview, DeskState, Finding, FusionRequest, RawEvent

MAX_AGE_H = 6.0
CONSUMER_GROUP = "fusion-desk"


class _Lane:
    """Trigger message for the fan-out (the lanes read the shared state)."""


class IngestWatch(LabNode):
    node = "ingest_watch"

    @handler
    async def start(self, req: FusionRequest, ctx: WorkflowContext[_Lane]) -> None:
        state = DeskState(run_id=req.run_id, region_id=req.region_id, window_end=req.window_end)
        hub: EventHubStandIn = self.deps["hub"]
        lake: DataLakeStandIn = self.deps["lake"]
        maps: MapsStandIn = self.deps["maps"]
        with self.enter(state):
            events = hub.receive(CONSUMER_GROUP)
            for ev in events:
                try:
                    raw = RawEvent.model_validate(ev.body)
                    cur = FUNCTIONS[raw.source](raw)
                except (ValidationError, Rejected, KeyError) as exc:
                    lake.write_json(
                        f"deadletter/{ev.partition}-{ev.sequence}.json", {"body": ev.body, "error": str(exc)}
                    )
                    state.issues.append(
                        f"dead-lettered event p{ev.partition}#{ev.sequence}: {type(exc).__name__}"
                    )
                    continue
                lake.write_json(f"raw/{raw.source}/{raw.region_id}/{raw.ts}.json", raw.model_dump())
                lake.write_json(f"curated/{cur.source}/{cur.region_id}/latest.json", cur.model_dump())
            hub.checkpoint(CONSUMER_GROUP, events)
            state.places = maps.context(req.region_id)

            def latest(source: str, region: str) -> dict | None:
                path = f"curated/{source}/{region}/latest.json"
                if path not in lake.files:
                    return None
                sig = lake.read_json(path)
                if hours_between(sig["ts"], req.window_end) > MAX_AGE_H:
                    state.issues.append(f"{source}@{region}: stale reading ignored")
                    return None
                return sig

            for s in SOURCES:
                if (sig := latest(s, req.region_id)) is not None:
                    state.signals[s] = sig
                    continue
                for nb, _km in state.places["neighbours"]:
                    if (nsig := latest(s, nb)) is not None:
                        state.neighbour_signals[s] = {"region_id": nb, **nsig}
                        break
            ctx.set_state("desk", state)
        await ctx.send_message(_Lane())


class _LaneNode(LabNode):
    async def _emit(self, ctx: WorkflowContext[Finding], finding: Finding) -> None:
        await ctx.send_message(finding)


class SeismicAnalysis(_LaneNode):
    node = "seismic_analysis"

    @handler
    async def run(self, _: _Lane, ctx: WorkflowContext[Finding]) -> None:
        st: DeskState = ctx.get_state("desk")
        f = SeismicAnalysisAgent().analyse(
            st.signals.get("seismic"), st.signals.get("displacement"), st.places["coastal"]
        )
        missing = {s: "prior" for s in ("seismic", "displacement") if s not in st.signals}
        await self._emit(ctx, f.model_copy(update={"fallbacks": {**f.fallbacks, **missing}}))


class SatelliteMonitoring(_LaneNode):
    node = "satellite_monitoring"

    @handler
    async def run(self, _: _Lane, ctx: WorkflowContext[Finding]) -> None:
        st: DeskState = ctx.get_state("desk")
        nb = st.neighbour_signals.get("satellite")
        f = SatelliteMonitoringAgent().analyse(
            st.signals.get("satellite"), st.places["coastal"], (nb["region_id"], nb) if nb else None
        )
        await self._emit(ctx, f)


class WeatherCorrelation(_LaneNode):
    node = "weather_correlation"

    @handler
    async def run(self, _: _Lane, ctx: WorkflowContext[Finding]) -> None:
        st: DeskState = ctx.get_state("desk")
        await self._emit(ctx, WeatherCorrelationAgent().analyse(st.signals.get("weather")))


class Join(LabNode):
    node = "join"

    @handler
    async def run(self, findings: list[Finding], ctx: WorkflowContext[DeskState]) -> None:
        st: DeskState = ctx.get_state("desk")
        with self.enter(st):
            st.findings = {f.agent: f.model_dump() for f in sorted(findings, key=lambda f: f.agent)}
        await ctx.send_message(st)


class HistoricalPattern(LabNode):
    node = "historical_pattern"

    @handler
    async def run(self, st: DeskState, ctx: WorkflowContext[DeskState]) -> None:
        agent: HistoricalPatternAgent = self.deps["history"]
        with self.enter(st):
            # leading hazard for the query = the one with the strongest raw evidence so far
            totals = {h: 0.0 for h in ("flood", "quake", "tsunami")}
            for f in st.findings.values():
                for h, per in f["evidence"].items():
                    totals[h] += sum(per.values())
            lead = max(totals, key=lambda h: totals[h])
            severity = max(0.0, min(1.0, totals[lead] / 10))
            st.analogs = agent.analogs(st.region_id, st.places["name"], lead, severity)
            st.fusion["base_rates"] = agent.base_rates(st.region_id)
        await ctx.send_message(st)


class Coordinator(LabNode):
    node = "prediction_coordinator"

    @handler
    async def run(self, st: DeskState, ctx: WorkflowContext[DeskState]) -> None:
        maps: MapsStandIn = self.deps["maps"]
        with self.enter(st):
            prior = maps.regions[st.region_id]["prior"]
            base = st.fusion.pop("base_rates")
            findings = [Finding.model_validate(f) for f in st.findings.values()]
            st.fusion = PredictionCoordinator().fuse(prior, findings, base, st.places["coastal"])
            st.risk = risk_mod.score(st.fusion, st.places)
            st.support = risk_mod.decision_support(st.risk, st.places, st.fusion)
        await ctx.send_message(st)


class SituationSummary(LabNode):
    node = "situation_summary"

    @handler
    async def run(self, st: DeskState, ctx: WorkflowContext[DeskState]) -> None:
        with self.enter(st):
            packet, issues = await self.deps["writer"].write(
                facts={"risk": st.risk, "places": st.places["name"]},
                draft=summary_mod.draft(st),
                check=summary_mod.check_factory(st),
            )
            st.summary = packet
            st.issues += issues
        await ctx.send_message(st)


class AlertDecision(LabNode):
    node = "alert_decision"

    @handler
    async def run(self, st: DeskState, ctx: WorkflowContext[DeskState, dict]) -> None:
        with self.enter(st):
            ctx.set_state("desk", st)
            await ctx.request_info(
                AlertReview(
                    run_id=st.run_id,
                    region_id=st.region_id,
                    primary_hazard=st.risk["primary_hazard"],
                    level=st.risk["level"],
                    risk=st.risk,
                    contributions=st.fusion["contributions"],
                    fallbacks=st.fusion["fallbacks"],
                    uncertainty=st.fusion["uncertainty"],
                    analog_ids=[a["record_id"] for a in st.analogs],
                    affected_facilities=st.support["affected_facilities"],
                    proposed=st.support["proposed"],
                    summary=st.summary,
                    decision_support=st.support,
                    issues=list(st.issues),
                ),
                Decision,
            )

    @response_handler
    async def on_decision(
        self, review: AlertReview, d: Decision, ctx: WorkflowContext[DeskState, dict]
    ) -> None:
        st: DeskState = ctx.get_state("desk")
        if d.approved and review.proposed == "recommend_warning_review":
            status = "handed_to_warning_officer"
        elif d.approved:
            status = "acknowledged_monitoring"
        else:
            status = "dismissed_by_reviewer"
        await ctx.yield_output(
            {
                "run_id": st.run_id,
                "region_id": st.region_id,
                "status": status,
                "public_alert_sent": False,  # there is no code path that sends one
                "reviewer": d.reviewer,
                "note": d.note,
                "primary_hazard": review.primary_hazard,
                "level": review.level,
                "risk": st.risk,
                "decision_support": st.support,
                "summary": st.summary,
                "trail": st.trail,
                "issues": st.issues,
                "state": asdict(st),
            }
        )


def build_workflow(**deps) -> Workflow:
    ingest = IngestWatch(**deps)
    lanes = [SeismicAnalysis(**deps), SatelliteMonitoring(**deps), WeatherCorrelation(**deps)]
    join, hist, coord = Join(**deps), HistoricalPattern(**deps), Coordinator(**deps)
    summ, decide = SituationSummary(**deps), AlertDecision(**deps)
    return (
        WorkflowBuilder(
            start_executor=ingest,
            name="disaster-signal-fusion",
            max_iterations=30,
            description="Multi-signal hazard fusion with a human alert decision",
        )
        .add_fan_out_edges(ingest, lanes)
        .add_fan_in_edges(lanes, join)
        .add_edge(join, hist)
        .add_edge(hist, coord)
        .add_edge(coord, summ)
        .add_edge(summ, decide)
        .build()
    )
