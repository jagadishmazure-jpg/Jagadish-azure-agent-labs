"""MAF workflow: Scans -> RAG -> Reasoning -> Explain -> ophthalmologist review.

scan_intake (image + metadata, schema check)
  -> embed (vision stand-in + OOD gate; denied scans stop here with a denial record)
  -> retrieve (similar labeled cases + reference reports, hybrid search)
  -> reason (constrained, calibrated hypotheses or abstain)
  -> explain (Foundry explainer; cites case ids)
  -> ophthalmologist_review (HITL request_info)
  -> research log entry (no EHR write-back exists in this lab)"""

from __future__ import annotations

import itertools

from agent_framework import Workflow, WorkflowBuilder, WorkflowContext, handler, response_handler
from pydantic import ValidationError

from eyescan import BANNER
from eyescan import explainer as ex
from eyescan.knowledge import OodGate
from eyescan.models import OphthalmologistReview, Scan, ScanState
from eyescan.reasoning import explain
from labcore.hitl import Decision
from labcore.workflow import LabNode


def _denial(st: ScanState, reasons: list[str]) -> dict:
    return {
        "run_id": st.run_id,
        "case_id": st.scan.get("case_id"),
        "status": "denied_out_of_distribution",
        "reasons": reasons,
        "hypotheses": [],
        "banner": BANNER,
        "ehr_written": False,
        "trail": st.trail,
    }


class ScanIntake(LabNode):
    node = "scan_intake"

    @handler
    async def run(self, req: dict, ctx: WorkflowContext[ScanState, dict]) -> None:
        st = ScanState(run_id=req["run_id"], scan={"case_id": req["scan"].get("case_id")})
        with self.enter(st):
            try:
                st.scan = Scan.model_validate(req["scan"]).model_dump()
            except ValidationError as exc:
                await ctx.yield_output(_denial(st, [f"invalid scan packet ({exc.error_count()} errors)"]))
                return
        await ctx.send_message(st)


class Embed(LabNode):
    node = "embed"

    @handler
    async def run(self, st: ScanState, ctx: WorkflowContext[ScanState, dict]) -> None:
        lib = self.deps["library"]
        with self.enter(st):
            try:
                st.features = lib.vision.features(st.scan["image"])
            except ValueError as exc:
                await ctx.yield_output(_denial(st, [str(exc)]))
                return
            st.embedding = lib.embed(st.features)
            st.ood = OodGate().check(st.scan, lib.nearest_distance(st.embedding), lib.ood_radius, st.features)
            if st.ood["denied"]:
                await ctx.yield_output(_denial(st, st.ood["reasons"]))
                return
        await ctx.send_message(st)


class Retrieve(LabNode):
    node = "retrieve"

    @handler
    async def run(self, st: ScanState, ctx: WorkflowContext[ScanState]) -> None:
        lib = self.deps["library"]
        with self.enter(st):
            st.similar = lib.similar(st.embedding, st.scan["metadata"])
            labels = list(dict.fromkeys(h["label"] for h in st.similar))
            st.references = lib.references(
                labels, " ".join(ex_f for ex_f in st.features if st.features[ex_f] > 1)
            )
        await ctx.send_message(st)


class Reason(LabNode):
    node = "reason"

    @handler
    async def run(self, st: ScanState, ctx: WorkflowContext[ScanState]) -> None:
        with self.enter(st):
            st.hypotheses, st.abstain = self.deps["reasoner"].hypotheses(
                st.similar, st.scan["metadata"], st.features
            )
            if st.hypotheses:
                st.contributions = explain(
                    self.deps["reasoner"], st.features, st.scan["metadata"], st.hypotheses[0]["label"]
                )
        await ctx.send_message(st)


class Explain(LabNode):
    node = "explain"

    @handler
    async def run(self, st: ScanState, ctx: WorkflowContext[ScanState]) -> None:
        with self.enter(st):
            st.report, issues = await self.deps["writer"].write(
                facts={"hypotheses": st.hypotheses, "abstain": st.abstain},
                draft=ex.draft(st),
                check=ex.check_factory(st),
            )
            st.issues += issues
        await ctx.send_message(st)


class OphthalmologistGate(LabNode):
    node = "ophthalmologist_review"

    @handler
    async def run(self, st: ScanState, ctx: WorkflowContext[ScanState, dict]) -> None:
        with self.enter(st):
            ctx.set_state("scan", st)
            await ctx.request_info(
                OphthalmologistReview(
                    run_id=st.run_id,
                    case_id=st.scan["case_id"],
                    banner=BANNER,
                    hypotheses=st.hypotheses,
                    abstain=st.abstain,
                    similar_case_ids=[h["case_id"] for h in st.similar],
                    report=st.report,
                    issues=list(st.issues),
                ),
                Decision,
            )

    @response_handler
    async def on_decision(
        self, review: OphthalmologistReview, d: Decision, ctx: WorkflowContext[ScanState, dict]
    ) -> None:
        st: ScanState = ctx.get_state("scan")
        final = d.overrides.get("final_label") or (
            st.hypotheses[0]["label"] if st.hypotheses and d.approved else None
        )
        entry = {
            "run_id": st.run_id,
            "case_id": st.scan["case_id"],
            "reviewer": d.reviewer,
            "approved": d.approved,
            "final_label": final,
            "model_top": st.hypotheses[0]["label"] if st.hypotheses else None,
            "note": d.note,
        }
        self.deps["research_log"].append(entry)
        await ctx.yield_output(
            {
                "run_id": st.run_id,
                "case_id": st.scan["case_id"],
                "status": "reviewed" if d.approved else "rejected_by_reviewer",
                "hypotheses": st.hypotheses,
                "abstain": st.abstain,
                "report": st.report,
                "final_label": final,
                "banner": BANNER,
                "ehr_written": False,
                "research_log_entry": entry,
                "trail": st.trail,
                "issues": st.issues,
            }
        )


def build_workflow(**deps) -> Workflow:
    nodes = [
        ScanIntake(**deps),
        Embed(**deps),
        Retrieve(**deps),
        Reason(**deps),
        Explain(**deps),
        OphthalmologistGate(**deps),
    ]
    b = WorkflowBuilder(
        start_executor=nodes[0],
        name="eye-scan-research",
        max_iterations=20,
        description="Research-only retinal scan triage with a human reader",
    )
    for a, c in itertools.pairwise(nodes):
        b = b.add_edge(a, c)
    return b.build()
