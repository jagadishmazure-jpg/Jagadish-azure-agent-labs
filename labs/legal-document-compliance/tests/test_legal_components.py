"""MCP servers, reliability scoring, extraction and classification."""

import pytest

from labcore.identity import MockManagedIdentityCredential
from labcore.middleware import ToolDenied
from labcore.search import HybridIndexStandIn
from legalcomp import extract
from legalcomp.classify import TAXONOMY, rule_label
from legalcomp.index import chunk, index_clauses
from legalcomp.mcp_servers import docintel, gateway
from legalcomp.models import LayoutResult
from legalcomp.reliability import score_page


async def test_mcp_servers_expose_small_read_only_surfaces():
    from mcp import Client

    async with Client(docintel) as c:
        names = [t.name for t in (await c.list_tools()).tools]
    assert names == ["analyze_layout"]


async def test_gateway_validates_layout_packet():
    out = await gateway().call(
        "docintel", "analyze_layout", {"doc_id": "bank-term-loan"}, schema=LayoutResult
    )
    assert out["domain"] == "banking" and out["pages"][0]["tables"]


async def test_identity_without_role_is_refused():
    gw = gateway(MockManagedIdentityCredential(client_id="mi-other", role_grants={}))
    with pytest.raises(ToolDenied):
        await gw.call("docintel", "analyze_layout", {"doc_id": "bank-term-loan"})


async def test_unknown_document_is_a_tool_error():
    from labcore.mcp_gateway import ToolCallError

    with pytest.raises(ToolCallError):
        await gateway().call("docintel", "analyze_layout", {"doc_id": "nope"})


def test_junk_page_rejected_clean_page_accepted():
    doc = extract.analyze_layout("hc-business-associate")
    scores = {p["page"]: score_page(p) for p in doc["pages"]}
    assert not scores[3]["accepted"] and scores[3]["junk_score"] > 0.35
    assert scores[1]["accepted"] and scores[2]["accepted"]


def test_clauses_never_stitched_across_rejected_page():
    doc = extract.analyze_layout("hc-business-associate")
    clauses = extract.segment_clauses("hc-business-associate", doc["pages"], [1, 2])
    assert all(3 not in c["pages"] for c in clauses)
    assert [c["clause_id"] for c in clauses][-1] == "hc-business-associate:s5"


def test_ragged_table_goes_to_review_not_dropped():
    doc = extract.analyze_layout("hc-privacy-notice")
    out = extract.normalise_tables(doc["pages"], [1, 2])
    assert out["tables"] == [] and out["needs_review"][0]["reason"].startswith("ragged")


def test_table_on_rejected_page_goes_to_review():
    doc = extract.analyze_layout("hc-business-associate")
    out = extract.normalise_tables(doc["pages"], [1, 2])
    assert out["needs_review"][0]["table_id"] == "hc-business-associate:t-fees"


@pytest.mark.parametrize(
    ("heading", "body", "label"),
    [
        ("KNOW YOUR CUSTOMER AND ANTI-MONEY LAUNDERING", "beneficial ownership", "kyc_aml"),
        ("BREACH NOTIFICATION", "notify within 10 days", "breach_notification"),
        ("LIMITS OF LIABILITY", "total liability will not exceed", "limitation_of_liability"),
        ("DEFINITIONS", "Borrower means Alder Tools", "other"),
    ],
)
def test_rule_labels(heading, body, label):
    assert rule_label(heading, body)[0] == label


def test_taxonomy_is_closed_and_includes_other():
    assert "other" in TAXONOMY and len(TAXONOMY) == 13


def test_clause_chunks_indexed_and_searchable():
    idx = HybridIndexStandIn("t")
    doc = extract.analyze_layout("ins-property-wording")
    clauses = extract.segment_clauses("ins-property-wording", doc["pages"], [1, 2])
    assert index_clauses(idx, "ins-property-wording", "insurance", clauses) >= len(clauses)
    assert (
        idx.search("flood excluded", filter={"domain": "insurance"})[0].doc["clause_id"]
        == "ins-property-wording:s2"
    )
    assert len(chunk(" ".join(["w"] * 95))) == 3
