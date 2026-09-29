"""Router, auditor (redo / escalate), compliance checklist and model selection."""

import json

from agent_framework import ChatResponse, Message

from labcore.foundry import MockFoundryChatClient
from legalcomp import extract
from legalcomp.model_selection import CANDIDATES, choose, table
from legalcomp.reliability import score_page
from legalcomp.routing import audit, route
from legalcomp.service import ComplianceDesk

DOCS = [
    "bank-term-loan",
    "bank-kyc-policy",
    "ins-property-wording",
    "ins-claims-standard",
    "hc-business-associate",
    "hc-privacy-notice",
]


def wrong_label_client():
    def script(msgs, opts):
        if opts.get("response_format") is None:
            return None
        text = next(m.text for m in reversed(msgs) if m.role == "user")
        cid = text.split('"clause_id": "')[1].split('"')[0]
        return ChatResponse(
            messages=[
                Message(
                    role="assistant",
                    contents=[
                        json.dumps({"clause_id": cid, "label": "confidentiality", "rationale": "guess"})
                    ],
                )
            ]
        )

    return MockFoundryChatClient(script=script)


def test_router_detects_domain_from_text_for_every_document():
    for d in DOCS:
        layout = extract.analyze_layout(d)
        r = route(layout, [score_page(p) for p in layout["pages"]])
        assert r["detected_domain"] == layout["domain"] and not r["mismatch"], d


def test_router_flags_declared_domain_mismatch_and_escalates_pages():
    layout = {**extract.analyze_layout("hc-business-associate"), "domain": "banking"}
    r = route(layout, [score_page(p) for p in layout["pages"]])
    assert r["mismatch"] and r["escalated_pages"] == [3]


def test_auditor_compliance_checklist_finds_missing_clause():
    out = audit(
        [
            {
                "clause_id": "x:s1",
                "label": "data_protection",
                "rule_label": "data_protection",
                "model_agrees": True,
                "margin": 1.0,
            }
        ],
        "healthcare",
        0,
    )
    assert out["action"] == "pass" and out["missing_required"] == ["breach_notification"]


async def test_auditor_requests_redo_and_second_deployment_fixes_labels():
    desk = ComplianceDesk(writer_client=wrong_label_client())
    res = await desk.review("bank-term-loan")
    p = res.pending
    assert p.audit["action"] == "pass"
    labels = {c["clause_id"]: c["label"] for c in p.clauses}
    assert labels["bank-term-loan:s4"] == "kyc_aml"
    assert any(c.get("redone") for c in p.clauses)


async def test_auditor_escalates_when_redo_also_disagrees():
    desk = ComplianceDesk(writer_client=wrong_label_client(), redo_client=wrong_label_client())
    res = await desk.review("ins-property-wording")
    p = res.pending
    assert p.audit["action"] == "escalate"
    assert all(c["needs_review"] for c in p.clauses if c.get("escalated"))
    assert any("escalated" in i for i in p.issues)


def test_model_selection_respects_ceilings_and_marks_mock_scores():
    assert choose("parsing").name == "Document Intelligence prebuilt-layout"
    assert choose("reasoning").name.startswith(
        "gpt-5-mini"
    )  # gpt-5 is better but over the latency/cost ceiling
    assert choose("legal_understanding").name == "lexicon rules + gpt-5-mini check"
    assert "mock" in table() and {c.source for c in CANDIDATES} == {"mock", "measured"}
