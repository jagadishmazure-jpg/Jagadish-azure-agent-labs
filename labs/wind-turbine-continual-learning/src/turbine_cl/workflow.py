"""MAF workflow for one turbine window. Memory is not learning:

    ingest (Event Hub stand-in)
      -> static_maintenance (Isolation Forest champion + pattern rules, read-only)  [normal: stop]
      -> episodic_memory (similar past incidents)
      -> context_gating (apply a PROMOTED lesson only if turbine model + pattern fit)
      -> evaluation (diagnosis + action quality, confidence)
      -> recommend (Foundry, catalog actions only)
      -> technician_review (HITL)
      -> learning_signals (was it right? structured feedback)
      -> continual_learning (candidate lesson + confirmed episode)

Nothing here fits, retrains or promotes a detector or a lesson; both go through eval gates
that a person runs (promotion.py, lessons.py)."""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any

from agent_framework import Workflow, WorkflowBuilder, WorkflowContext, handler, response_handler

from labcore.hitl import Decision
from labcore.workflow import LabNode, RunState
from turbine_cl import diagnose as dx
from turbine_cl.agents import (
    ContextGatingAgent,
    ContinualLearningAgent,
    EpisodicMemoryAgent,
    EvaluationAgent,
    LearningSignalsAgent,
    StaticMaintenanceAgent,
)
from turbine_cl.context import turbine_context


@dataclass
class TurbineState(RunState):
    turbine_id: str = ""
    rows: list[dict] = field(default_factory=list)
    detector_version: str = ""
    detection: dict[str, Any] = field(default_factory=dict)
    similar: list[dict] = field(default_factory=list)
    diagnosis: str = ""
    confidence: float = 0.0
    recommendation: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    memory: dict[str, Any] = field(default_factory=dict)
    gating: dict[str, Any] = field(default_factory=dict)
    evaluation: dict[str, Any] = field(default_factory=dict)
    outcome: dict[str, Any] = field(default_factory=dict)
    signal: dict[str, Any] | None = None
    decision: Any = None


@dataclass
class TechnicianReview:
    run_id: str
    turbine_id: str
    detector_version: str
    detection: dict[str, Any]
    similar: list[dict]
    diagnosis: str
    confidence: float
    recommendation: dict[str, Any]
    issues: list[str]
    context: dict[str, Any]
    evaluation: dict[str, Any]
    gating: dict[str, Any]


class Ingest(LabNode):
    node = "ingest"

    @handler
    async def run(self, req: dict, ctx: WorkflowContext[TurbineState]) -> None:
        st = TurbineState(run_id=req["run_id"], turbine_id=req["turbine_id"])
        hub = self.deps["hub"]
        with self.enter(st):
            events = [e for e in hub.receive("diagnostics") if e.body["turbine_id"] == st.turbine_id]
            hub.checkpoint("diagnostics", events)
            st.rows = sorted((e.body for e in events), key=lambda r: r["t"])[-6:]
        await ctx.send_message(st)


class StaticMaintenance(LabNode):
    """Agent 1: Isolation Forest champion (read-only) + residual pattern rules."""

    node = "static_maintenance"

    @handler
    async def run(self, st: TurbineState, ctx: WorkflowContext[TurbineState, dict]) -> None:
        with self.enter(st):
            det, entry = self.deps["detector"]
            st.detector_version = entry["version"]
            st.context = turbine_context(st.turbine_id, st.rows)
            if len(st.rows) < 3:
                await ctx.yield_output(
                    {
                        "run_id": st.run_id,
                        "turbine_id": st.turbine_id,
                        "status": "insufficient_data",
                        "rows": len(st.rows),
                        "episode_written": False,
                    }
                )
                return
            st.detection = StaticMaintenanceAgent(det).run(st.rows)
            if not st.detection["anomalous"]:
                await ctx.yield_output(
                    {
                        "run_id": st.run_id,
                        "turbine_id": st.turbine_id,
                        "status": "no_anomaly",
                        "detector_version": st.detector_version,
                        "detection": st.detection,
                        "episode_written": False,
                    }
                )
                return
        await ctx.send_message(st)


class EpisodicMemory(LabNode):
    """Agent 2: retrieve similar past incidents; memory proposes, it does not learn."""

    node = "episodic_memory"

    @handler
    async def run(self, st: TurbineState, ctx: WorkflowContext[TurbineState]) -> None:
        with self.enter(st):
            st.memory = EpisodicMemoryAgent(self.deps["episodes"]).run(
                st.detection["signature"], st.context, st.detection["pattern"]
            )
            st.similar = st.memory["similar"]
        await ctx.send_message(st)


class ContextGating(LabNode):
    """Agent 6 (applied online): use a promoted lesson only when turbine model and pattern fit."""

    node = "context_gating"

    @handler
    async def run(self, st: TurbineState, ctx: WorkflowContext[TurbineState]) -> None:
        with self.enter(st):
            g = ContextGatingAgent(self.deps["lessons"]).run(
                st.memory["memory_diagnosis"], st.context, st.detection["signature"]
            )
            st.gating, st.diagnosis = g, g["diagnosis"]
        await ctx.send_message(st)


class Evaluate(LabNode):
    """Agent 3 (before the technician): check diagnosis + action quality and set confidence."""

    node = "evaluation"

    @handler
    async def run(self, st: TurbineState, ctx: WorkflowContext[TurbineState]) -> None:
        with self.enter(st):
            st.evaluation = EvaluationAgent().pre(
                st.detection, st.memory, st.diagnosis, dx.CATALOG[st.diagnosis], st.context
            )
            if st.gating["lesson_applied"]:
                st.evaluation["checks"]["static_and_memory_agree"] = (
                    True  # overridden on purpose by a gated lesson
                )
                st.evaluation["confidence"] = max(st.evaluation["confidence"], 0.8)
            st.confidence = st.evaluation["confidence"]
        await ctx.send_message(st)


class Recommend(LabNode):
    node = "recommend"

    @handler
    async def run(self, st: TurbineState, ctx: WorkflowContext[TurbineState]) -> None:
        with self.enter(st):
            st.recommendation, issues = await self.deps["writer"].write(
                facts={"diagnosis": st.diagnosis, "catalog": dx.CATALOG[st.diagnosis]},
                draft=dx.draft(
                    st.turbine_id,
                    st.diagnosis,
                    st.confidence,
                    st.similar,
                    st.detection["top_features"],
                    st.detection["contributions"],
                ),
                check=dx.check_factory(st.diagnosis, st.similar),
            )
            st.issues += issues
        await ctx.send_message(st)


class TechnicianGate(LabNode):
    node = "technician_review"

    @handler
    async def run(self, st: TurbineState, ctx: WorkflowContext[TurbineState, dict]) -> None:
        with self.enter(st):
            ctx.set_state("turbine", st)
            await ctx.request_info(
                TechnicianReview(
                    st.run_id,
                    st.turbine_id,
                    st.detector_version,
                    st.detection,
                    st.similar,
                    st.diagnosis,
                    st.confidence,
                    st.recommendation,
                    list(st.issues),
                    st.context,
                    st.evaluation,
                    st.gating,
                ),
                Decision,
            )

    @response_handler
    async def on_decision(
        self, review: TechnicianReview, d: Decision, ctx: WorkflowContext[TurbineState]
    ) -> None:
        st: TurbineState = ctx.get_state("turbine")
        st.decision = d
        confirmed = d.overrides.get("confirmed_diagnosis") or (st.diagnosis if d.approved else "false_alarm")
        st.outcome = EvaluationAgent().post(st.diagnosis, confirmed, d.approved)
        await ctx.send_message(st)


class LearningSignals(LabNode):
    """Agent 3 (after) + Agent 4: was it right? If not, emit a structured feedback record."""

    node = "learning_signals"

    @handler
    async def run(self, st: TurbineState, ctx: WorkflowContext[TurbineState]) -> None:
        with self.enter(st):
            st.signal = LearningSignalsAgent().run(
                st.outcome, st.evaluation, st.context, st.detection["signature"]
            )
        await ctx.send_message(st)


class ContinualLearning(LabNode):
    """Agent 5: distil a candidate lesson and write the confirmed episode. Never promotes anything."""

    node = "continual_learning"

    @handler
    async def run(self, st: TurbineState, ctx: WorkflowContext[TurbineState, dict]) -> None:
        with self.enter(st):
            d: Decision = st.decision
            candidate = ContinualLearningAgent().run(st.signal, self.deps["lesson_candidates"])
            confirmed = st.outcome["confirmed"]
            episode = {
                "episode_id": f"EP-{st.run_id}",
                "turbine_id": st.turbine_id,
                "turbine_model": st.context["turbine_model"],
                "diagnosis": confirmed,
                "model_diagnosis": st.diagnosis,
                "signature": st.detection["signature"],
                "actions": dx.CATALOG.get(confirmed, []),
                "note": d.note,
                "confirmed_by": d.reviewer,
                "detector_version": st.detector_version,
            }
            self.deps["episodes"].write(episode)
        await ctx.yield_output(
            {
                "run_id": st.run_id,
                "turbine_id": st.turbine_id,
                "status": "actioned"
                if d.approved
                else ("corrected" if confirmed != "false_alarm" else "closed_false_alarm"),
                "diagnosis": confirmed,
                "proposed_diagnosis": st.diagnosis,
                "confidence": st.confidence,
                "recommendation": st.recommendation,
                "evaluation": {"before_review": st.evaluation, "after_review": st.outcome},
                "learning_signal": st.signal,
                "lesson_candidate": candidate,
                "lesson_applied": st.gating.get("lesson_applied"),
                "episode_written": True,
                "episode": episode,
                "trail": st.trail,
                "detector_version": st.detector_version,
            }
        )


def build_workflow(**deps) -> Workflow:
    nodes = [
        Ingest(**deps),
        StaticMaintenance(**deps),
        EpisodicMemory(**deps),
        ContextGating(**deps),
        Evaluate(**deps),
        Recommend(**deps),
        TechnicianGate(**deps),
        LearningSignals(**deps),
        ContinualLearning(**deps),
    ]
    b = WorkflowBuilder(
        start_executor=nodes[0],
        name="turbine-diagnostics",
        max_iterations=20,
        description="Telemetry anomaly to technician-confirmed episode",
    )
    for a, c in itertools.pairwise(nodes):
        b = b.add_edge(a, c)
    return b.build()
