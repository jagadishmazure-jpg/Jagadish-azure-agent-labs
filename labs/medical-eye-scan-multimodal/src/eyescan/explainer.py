"""Explainer (Foundry, mocked): turns the computed hypotheses into a short research report that must
cite the retrieved case ids and reference notes, and must carry the not-a-medical-device banner."""

from __future__ import annotations

from eyescan import BANNER
from eyescan.models import ExplanationReport
from labcore.explain import render
from labcore.foundry import FoundryDeployment, FoundryWriter
from labcore.middleware import deny_tools

DEPLOYMENT = FoundryDeployment(
    "eye-explainer", model="gpt-5-mini", data_zone="us", purpose="research explanation"
)
DENIED = ("ehr_*", "fhir_*", "*write_back*", "*order_*", "*prescribe*")
INSTRUCTIONS = (
    "You explain an automated research triage of a synthetic retinal array to an ophthalmologist. "
    "Only use the hypotheses, findings and ids provided; cite case ids and reference ids; never state a "
    "diagnosis as fact; always keep the banner."
)


def make_writer(client=None) -> FoundryWriter:
    return FoundryWriter(
        "eye-explainer",
        INSTRUCTIONS,
        ExplanationReport,
        DEPLOYMENT,
        client=client,
        middleware=[deny_tools(DENIED)],
    )


def draft(state) -> dict:
    top = state.hypotheses[0] if state.hypotheses else None
    if state.abstain or top is None:
        summary = "Low confidence: no hypothesis clears the threshold; refer for a full human read."
    else:
        summary = (
            f"Most similar labeled cases point to {top['label'].replace('_', ' ')} "
            f"(calibrated confidence {top['confidence']:.2f})."
        )
    return {
        "banner": BANNER,
        "summary": summary,
        "findings": top["findings"] if top else [],
        "cited_case_ids": [h["case_id"] for h in state.similar],
        "cited_reference_ids": [r["ref_id"] for r in state.references],
        "feature_contributions": [
            f"{line} ({state.contributions['method']})" for line in render(state.contributions)
        ]
        if state.contributions
        else [],
        "limitations": "Synthetic 16x16 arrays and hand-made features; not validated on real images.",
    }


def check_factory(state):
    allowed = {h["case_id"] for h in state.similar}
    refs = {r["ref_id"] for r in state.references}

    def check(r: ExplanationReport) -> list[str]:
        p = []
        if not r.cited_case_ids:
            p.append("no case ids cited")
        if not set(r.cited_case_ids) <= allowed:
            p.append(f"cites cases that were not retrieved: {sorted(set(r.cited_case_ids) - allowed)}")
        if not set(r.cited_reference_ids) <= refs:
            p.append("cites unknown reference ids")
        if "NOT A MEDICAL DEVICE" not in r.banner:
            p.append("banner missing")
        return p

    return check
