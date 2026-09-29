import importlib.util
import json
from pathlib import Path

import pytest
from agent_framework import ChatResponse, Message

from labcore.foundry import MockFoundryChatClient
from labcore.hitl import Decision
from labcore.infra_check import build, find_bicep
from legalcomp.card import CARD
from legalcomp.service import ComplianceDesk

LAB = Path(__file__).resolve().parents[1]


async def test_banking_contract_end_to_end():
    desk = ComplianceDesk()
    res = await desk.review("bank-term-loan")
    p = res.pending
    assert {c["clause_id"] for c in p.clauses} == {f"bank-term-loan:s{i}" for i in range(2, 7)}
    assert p.tables[0]["header"] == ["Instalment", "Due month", "Principal (USD)"]
    assert all(c["label"] != "other" for c in p.clauses)


async def test_healthcare_junk_page_forces_review_items():
    desk = ComplianceDesk()
    res = await desk.review("hc-business-associate")
    p = res.pending
    assert p.rejected_pages == [3] and p.uncertainty >= 0.9
    assert any(i.startswith("page 3") for i in p.review_items)
    assert any("t-fees" in i for i in p.review_items)


async def test_reviewer_relabel_and_no_write_back():
    desk = ComplianceDesk()
    res = await desk.review("ins-claims-standard")
    out = (
        await desk.decide(
            res.run_id,
            res.request_id,
            Decision(
                True,
                "counsel-ng",
                overrides={"relabel": {"ins-claims-standard:s4": "limitation_of_liability"}},
            ),
        )
    ).output
    lab = {c["clause_id"]: c["label"] for c in out["clauses"]}
    assert lab["ins-claims-standard:s4"] == "limitation_of_liability"
    assert out["contract_system_updated"] is False


async def test_model_label_outside_taxonomy_is_rejected():
    def rogue(_m, opts):
        if opts.get("response_format") is not None:
            return ChatResponse(
                messages=[
                    Message(
                        role="assistant",
                        contents=['{"clause_id": "x", "label": "totally_fine", "rationale": "trust me"}'],
                    )
                ]
            )
        return None

    desk = ComplianceDesk(writer_client=MockFoundryChatClient(script=rogue))
    res = await desk.review("ins-property-wording")
    assert all(c["label"] != "totally_fine" for c in res.pending.clauses)
    assert res.pending.issues


async def test_dropped_table_would_fail_loudly(monkeypatch):
    from legalcomp import extract
    from legalcomp.workflow import TablesDropped

    orig = extract.normalise_tables
    monkeypatch.setattr(
        extract,
        "normalise_tables",
        lambda pages, acc, min_conf=0.8: {**orig(pages, acc, min_conf), "needs_review": []},
    )
    desk = ComplianceDesk()
    with pytest.raises(TablesDropped):
        await desk.review("hc-privacy-notice")


def _eval():
    spec = importlib.util.spec_from_file_location("legal_eval", LAB / "evals" / "run_eval.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


async def test_eval_gate_passes_all_domains():
    rep = await _eval().evaluate()
    assert rep.passed, rep.failures
    for dom in ("banking", "insurance", "healthcare"):
        assert rep.metrics[f"{dom}_recall"] == 1.0


async def test_gate_fails_when_clause_ids_drift(monkeypatch):
    from legalcomp import extract

    orig = extract.segment_clauses

    def off_by_one(doc_id, pages, acc):
        return [{**c, "clause_id": f"{doc_id}:s{c['section'] + 1}"} for c in orig(doc_id, pages, acc)]

    monkeypatch.setattr(extract, "segment_clauses", off_by_one)
    rep = await _eval().evaluate()
    assert not rep.passed and rep.metrics["clause_precision"] < 0.95


def test_agent_card_current():
    path = LAB.parents[1] / "control-plane" / "agent-cards" / "legal-document-compliance.json"
    assert json.loads(path.read_text()) == CARD


@pytest.mark.skipif(find_bicep() is None, reason="bicep CLI not installed")
def test_bicep_compiles():
    res = build(LAB / "infra" / "main.bicep")
    assert res.returncode == 0, res.stderr
