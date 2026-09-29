"""MAF workflow for one document.

parse (MCP docintel) -> reliability (page junk scores) -> router (domain profile, page escalation)
    ├─> clause_extract (MCP clauses) ─┐   handoff to the extraction tools
    └─> table_extract  (MCP tables)  ─┴─> join (table accounting invariant)
-> index (AI Search stand-in) -> classify (Foundry, taxonomy-constrained)
-> auditor ─(redo, at most once)─> classify      regeneration on the second deployment
         └─(pass / escalate)──> uncertainty -> compliance_review (HITL request_info)"""

from __future__ import annotations

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
from legalcomp import classify as cls
from legalcomp.index import index_clauses
from legalcomp.models import ClauseList, ComplianceReview, DocState, LayoutResult, TableResult
from legalcomp.reliability import score_page
from legalcomp.routing import audit, route

REVIEW_ABOVE = 0.35


class TablesDropped(RuntimeError):
    """Raised if any table from the parser is neither extracted nor queued for review."""


class Parse(LabNode):
    node = "parse"

    @handler
    async def run(self, req: dict, ctx: WorkflowContext[DocState]) -> None:
        st = DocState(run_id=req["run_id"], doc_id=req["doc_id"])
        with self.enter(st):
            raw = await self.deps["gateway"].call(
                "docintel", "analyze_layout", {"doc_id": st.doc_id}, schema=LayoutResult
            )
            st.layout = raw
        await ctx.send_message(st)


class Reliability(LabNode):
    node = "reliability"

    @handler
    async def run(self, st: DocState, ctx: WorkflowContext[DocState]) -> None:
        with self.enter(st):
            st.reliability = [score_page(p) for p in st.layout["pages"]]
            for r in st.reliability:
                if not r["accepted"]:
                    st.issues.append(f"page {r['page']} rejected: {r['reason']}")
        await ctx.send_message(st)


class Router(LabNode):
    node = "router"

    @handler
    async def run(self, st: DocState, ctx: WorkflowContext[str]) -> None:
        with self.enter(st):
            st.route = route(st.layout, st.reliability)
            if st.route["mismatch"]:
                st.issues.append(
                    f"router: text reads as {st.route['detected_domain']}, declared {st.route['declared_domain']}"
                )
            ctx.set_state("doc", st)
        await ctx.send_message("extract")


def _accepted(st: DocState) -> list[int]:
    return [r["page"] for r in st.reliability if r["accepted"]]


class ClauseExtract(LabNode):
    node = "clause_extract"

    @handler
    async def run(self, _: str, ctx: WorkflowContext[dict]) -> None:
        st: DocState = ctx.get_state("doc")
        out = await self.deps["gateway"].call(
            "clauses",
            "extract_clauses",
            {"doc_id": st.doc_id, "accepted_pages": _accepted(st)},
            schema=ClauseList,
        )
        await ctx.send_message({"lane": "clauses", **out})


class TableExtract(LabNode):
    node = "table_extract"

    @handler
    async def run(self, _: str, ctx: WorkflowContext[dict]) -> None:
        st: DocState = ctx.get_state("doc")
        out = await self.deps["gateway"].call(
            "tables",
            "extract_tables",
            {"doc_id": st.doc_id, "accepted_pages": _accepted(st)},
            schema=TableResult,
        )
        await ctx.send_message({"lane": "tables", **out})


class Join(LabNode):
    node = "join"

    @handler
    async def run(self, lanes: list[dict], ctx: WorkflowContext[DocState]) -> None:
        st: DocState = ctx.get_state("doc")
        with self.enter(st):
            by = {x["lane"]: x for x in lanes}
            st.clauses = by["clauses"]["clauses"]
            st.tables = by["tables"]["tables"]
            st.tables_for_review = by["tables"]["needs_review"]
            parsed = {t["table_id"] for p in st.layout["pages"] for t in p["tables"]}
            accounted = {t["table_id"] for t in st.tables} | {t["table_id"] for t in st.tables_for_review}
            if parsed != accounted:
                raise TablesDropped(f"{st.doc_id}: tables unaccounted for: {sorted(parsed - accounted)}")
        await ctx.send_message(st)


class Index(LabNode):
    node = "index"

    @handler
    async def run(self, st: DocState, ctx: WorkflowContext[DocState]) -> None:
        with self.enter(st):
            index_clauses(self.deps["index"], st.doc_id, st.layout["domain"], st.clauses)
        await ctx.send_message(st)


class Classify(LabNode):
    node = "classify"

    @handler
    async def run(self, st: DocState, ctx: WorkflowContext[DocState]) -> None:
        redo_ids = set(st.audit.get("redo_ids", []))
        writer = self.deps["redo_writer"] if redo_ids else self.deps["writer"]
        with self.enter(st):
            done = {c["clause_id"]: c for c in st.classified if c["clause_id"] not in redo_ids}
            out = []
            for c in st.clauses:
                if c["clause_id"] in done:
                    out.append(done[c["clause_id"]])
                    continue
                label, margin = cls.rule_label(c["heading"], c["text"])
                packet, issues = await writer.write(
                    facts={
                        "heading": c["heading"],
                        "text": c["text"][:600],
                        "domain_profile": st.route.get("profile"),
                    },
                    draft={
                        "clause_id": c["clause_id"],
                        "label": label,
                        "rationale": f"lexicon match on heading '{c['heading'].lower()}' (margin {margin})",
                    },
                    check=cls.check_factory(c["clause_id"]),
                )
                st.issues += issues
                out.append(
                    {
                        **c,
                        "label": packet["label"],
                        "rule_label": label,
                        "rationale": packet["rationale"],
                        "margin": margin,
                        "model_agrees": packet["label"] == label,
                        "redone": c["clause_id"] in redo_ids,
                    }
                )
            st.classified = out
            if redo_ids:
                st.redo_count += 1
        await ctx.send_message(st)


class Auditor(LabNode):
    node = "auditor"

    @handler
    async def run(self, st: DocState, ctx: WorkflowContext[DocState]) -> None:
        with self.enter(st):
            st.audit = audit(
                st.classified, st.route.get("detected_domain", st.layout["domain"]), st.redo_count
            )
            if st.audit["action"] == "escalate":
                for c in st.classified:
                    if c["clause_id"] in st.audit["escalated_clauses"]:
                        c["label"], c["escalated"] = c["rule_label"], True
                st.issues.append(
                    f"auditor escalated {len(st.audit['escalated_clauses'])} clause(s) after redo"
                )
        await ctx.send_message(st)


class Uncertainty(LabNode):
    node = "uncertainty"

    @handler
    async def run(self, st: DocState, ctx: WorkflowContext[DocState]) -> None:
        with self.enter(st):
            for c in st.classified:
                u = 1 - c["ocr_confidence"] * min(1.0, 0.5 + c["margin"]) * (
                    1.0 if c["model_agrees"] else 0.6
                )
                c["uncertainty"] = round(u, 3)
                c["needs_review"] = u > REVIEW_ABOVE or c.get("escalated", False)
            rejected = [r for r in st.reliability if not r["accepted"]]
            st.uncertainty = round(
                max([c["uncertainty"] for c in st.classified] + [0.9 if rejected else 0.0]), 3
            )
        await ctx.send_message(st)


class ComplianceGate(LabNode):
    node = "compliance_review"

    @handler
    async def run(self, st: DocState, ctx: WorkflowContext[DocState, dict]) -> None:
        with self.enter(st):
            ctx.set_state("doc", st)
            items = [
                f"clause {c['clause_id']} uncertainty {c['uncertainty']}"
                for c in st.classified
                if c["needs_review"]
            ]
            items += [f"table {t['table_id']}: {t['reason']}" for t in st.tables_for_review]
            items += [f"page {r['page']}: {r['reason']}" for r in st.reliability if not r["accepted"]]
            items += [f"audit: {f}" for f in st.audit.get("findings", []) if f.startswith("compliance check")]
            compliance = [c for c in st.classified if c["label"] != "other"]
            await ctx.request_info(
                ComplianceReview(
                    run_id=st.run_id,
                    doc_id=st.doc_id,
                    domain=st.layout["domain"],
                    clauses=compliance,
                    tables=st.tables,
                    tables_for_review=st.tables_for_review,
                    rejected_pages=[r["page"] for r in st.reliability if not r["accepted"]],
                    review_items=items,
                    route=st.route,
                    audit=st.audit,
                    uncertainty=st.uncertainty,
                    issues=list(st.issues),
                ),
                Decision,
            )

    @response_handler
    async def on_decision(
        self, review: ComplianceReview, d: Decision, ctx: WorkflowContext[DocState, dict]
    ) -> None:
        relabel = d.overrides.get("relabel", {})
        clauses = [{**c, "label": relabel.get(c["clause_id"], c["label"])} for c in review.clauses]
        await ctx.yield_output(
            {
                "run_id": review.run_id,
                "doc_id": review.doc_id,
                "status": "accepted" if d.approved else "returned",
                "reviewer": d.reviewer,
                "clauses": clauses,
                "tables": review.tables,
                "tables_for_review": review.tables_for_review,
                "rejected_pages": review.rejected_pages,
                "contract_system_updated": False,
            }
        )


def build_workflow(**deps) -> Workflow:
    parse, rel, router = Parse(**deps), Reliability(**deps), Router(**deps)
    ce, te, join = ClauseExtract(**deps), TableExtract(**deps), Join(**deps)
    idx, clf, aud = Index(**deps), Classify(**deps), Auditor(**deps)
    unc, gate = Uncertainty(**deps), ComplianceGate(**deps)
    return (
        WorkflowBuilder(
            start_executor=parse,
            name="legal-compliance",
            max_iterations=20,
            description="Contract/policy parsing with reliability scoring and reviewer sign-off",
        )
        .add_edge(parse, rel)
        .add_edge(rel, router)
        .add_fan_out_edges(router, [ce, te])
        .add_fan_in_edges([ce, te], join)
        .add_edge(join, idx)
        .add_edge(idx, clf)
        .add_edge(clf, aud)
        .add_switch_case_edge_group(
            aud,
            [
                Case(
                    condition=lambda s: isinstance(s, DocState) and s.audit.get("action") == "redo",
                    target=clf,
                ),
                Default(target=unc),
            ],
        )
        .add_edge(unc, gate)
        .build()
    )
