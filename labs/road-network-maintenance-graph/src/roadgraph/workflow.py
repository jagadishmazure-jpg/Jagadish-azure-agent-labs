"""Planning Coordinator + four graph agents on MAF. Flow: topology -> paths -> priority -> impact.

    planning_coordinator ─(next)─> graph_engineering ─┐   NetworkX nodes, edges, weights
            ▲            ─(next)─> graph_features ────┤   shortest paths, centrality, connectivity
            │            ─(next)─> maintenance_priority┤   condition need x criticality
            │            ─(next)─> closure_impact ─────┤   simulate closures, reroute, affected segments
            └──────────────────────────────────────────┘
    planning_coordinator ─(default: plan committed through BudgetGuard)─> narrative ─> engineer_review (HITL)

The NetworkX graph lives in a per-run `runtime` dict (not in messages); messages carry `PlanState`."""

from __future__ import annotations

import networkx as nx
from agent_framework import (
    Case,
    Default,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    handler,
    response_handler,
)

from labcore.hitl import Decision
from labcore.workflow import LabNode
from roadgraph import graph_ops as ops
from roadgraph import narrative as nar
from roadgraph.harness import BudgetExceeded, BudgetGuard, select_plan
from roadgraph.models import EngineerReview, PlanRequest, PlanState

ORDER = ["graph_engineering", "graph_features", "maintenance_priority", "closure_impact"]
MIN_SCORE = 0.05


class PlanningCoordinator(LabNode):
    node = "planning_coordinator"

    @handler
    async def start(self, req: PlanRequest, ctx: WorkflowContext[PlanState]) -> None:
        st = PlanState(
            run_id=req.run_id,
            budget_usd=req.budget_usd,
            closed_segments=list(req.closed_segments),
            what_if=list(req.what_if),
        )
        self.deps["runtime"]["guard"] = BudgetGuard(req.budget_usd)
        await self.route(st, ctx)

    @handler
    async def route(self, st: PlanState, ctx: WorkflowContext[PlanState]) -> None:
        with self.enter(st):
            pending = [t for t in ORDER if t not in st.done]
            if pending:
                st.next = pending[0]
                self.deps["runtime"]["guard"].worker(st.next)
            else:
                st.next = "narrative"
                st.plan = select_plan(
                    st.ranked, st.impacts, self.deps["runtime"]["guard"], min_score=MIN_SCORE
                )
                st.plan["road_health"] = st.health
        await ctx.send_message(st)


class _Agent(LabNode):
    async def finish(self, st: PlanState, ctx: WorkflowContext[PlanState]) -> None:
        st.done.append(self.node)
        await ctx.send_message(st)


class GraphEngineering(_Agent):
    node = "graph_engineering"

    @handler
    async def run(self, st: PlanState, ctx: WorkflowContext[PlanState]) -> None:
        with self.enter(st):
            g = ops.build_graph()
            for seg in st.closed_segments:
                g.remove_edge(*ops.edge_by_id(g, seg))
            self.deps["runtime"]["graph"] = g
            st.graph_summary = {
                "nodes": g.number_of_nodes(),
                "edges": g.number_of_edges(),
                "connected": nx.is_connected(g),
                "already_closed": st.closed_segments,
            }
        await self.finish(st, ctx)


class GraphFeatures(_Agent):
    node = "graph_features"

    @handler
    async def run(self, st: PlanState, ctx: WorkflowContext[PlanState]) -> None:
        rt = self.deps["runtime"]
        with self.enter(st):
            g = rt["graph"]
            dem = [d for d in ops.demand() if nx.has_path(g, d["origin"], d["dest"])]
            if dropped := len(ops.demand()) - len(dem):
                st.issues.append(f"{dropped} demand pairs already disconnected by existing closures")
            rt["demand"], rt["base"] = dem, ops.trip_minutes(g, dem)
            st.features = ops.features(g, dem)
            st.health = ops.road_health(g, st.features)
        await self.finish(st, ctx)


class MaintenancePriority(_Agent):
    node = "maintenance_priority"

    @handler
    async def run(self, st: PlanState, ctx: WorkflowContext[PlanState]) -> None:
        with self.enter(st):
            st.ranked = ops.priority(self.deps["runtime"]["graph"], st.features)
        await self.finish(st, ctx)


class ClosureImpact(_Agent):
    node = "closure_impact"

    @handler
    async def run(self, st: PlanState, ctx: WorkflowContext[PlanState]) -> None:
        rt = self.deps["runtime"]
        with self.enter(st):
            g = rt["graph"]
            targets = [r["segment_id"] for r in st.ranked if r["score"] >= MIN_SCORE] + st.what_if
            st.impacts = {
                s: ops.closure_impact(g, s, rt["demand"], rt["base"]) for s in dict.fromkeys(targets)
            }
        await self.finish(st, ctx)


class Narrative(LabNode):
    node = "narrative"

    @handler
    async def run(self, st: PlanState, ctx: WorkflowContext[PlanState]) -> None:
        with self.enter(st):
            st.narrative, issues = await self.deps["writer"].write(
                facts={"plan": [i["segment_id"] for i in st.plan["items"]], "health": st.health},
                draft=nar.draft(st.plan),
                check=nar.check_factory(st.plan),
            )
            st.issues += issues
        await ctx.send_message(st)


class EngineerGate(LabNode):
    node = "engineer_review"

    @handler
    async def run(self, st: PlanState, ctx: WorkflowContext[PlanState, dict]) -> None:
        with self.enter(st):
            ctx.set_state("plan", st)
            await ctx.request_info(
                EngineerReview(
                    st.run_id, st.plan, st.narrative, st.ranked[:5], st.impacts, st.health, list(st.issues)
                ),
                Decision,
            )

    @response_handler
    async def on_decision(
        self, review: EngineerReview, d: Decision, ctx: WorkflowContext[PlanState, dict]
    ) -> None:
        st: PlanState = ctx.get_state("plan")
        drop = set(d.overrides.get("remove_segments", []))
        items = [i for i in st.plan["items"] if i["segment_id"] not in drop]
        await ctx.yield_output(
            {
                "run_id": st.run_id,
                "status": "approved" if d.approved else "returned_for_rework",
                "reviewer": d.reviewer,
                "maintenance_plan": items if d.approved else [],
                "total_cost_usd": sum(i["cost_usd"] for i in items) if d.approved else 0,
                "closure_impacts": {s: st.impacts[s] for s in st.what_if}
                | {i["segment_id"]: i["impact"] for i in items},
                "road_health_report": st.health,
                "work_orders_issued": False,  # the lab hands an approved plan back; it never issues orders
                "narrative": st.narrative,
                "trail": st.trail,
                "issues": st.issues,
            }
        )


def build_workflow(**deps) -> Workflow:
    deps.setdefault("runtime", {})
    coord = PlanningCoordinator(**deps)
    agents = {
        a.node: a
        for a in (
            GraphEngineering(**deps),
            GraphFeatures(**deps),
            MaintenancePriority(**deps),
            ClosureImpact(**deps),
        )
    }
    narr, gate = Narrative(**deps), EngineerGate(**deps)
    b = WorkflowBuilder(
        start_executor=coord,
        name="road-maintenance",
        max_iterations=40,
        description="Planning coordinator and graph agents under a budget harness",
    )
    b = b.add_switch_case_edge_group(
        coord,
        [
            Case(condition=(lambda s, n=n: isinstance(s, PlanState) and s.next == n), target=a)
            for n, a in agents.items()
        ]
        + [Default(target=narr)],
    )
    for a in agents.values():
        b = b.add_edge(a, coord)
    return b.add_edge(narr, gate).build()


__all__ = ["BudgetExceeded", "build_workflow"]
