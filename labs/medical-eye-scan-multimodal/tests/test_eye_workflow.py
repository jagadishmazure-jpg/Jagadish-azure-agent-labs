"""End-to-end graph runs through the research desk."""

import json

from agent_framework import ChatResponse, Message, tool

from eyescan import BANNER, DATA
from eyescan.explainer import DENIED
from eyescan.service import ResearchDesk
from labcore.foundry import MockFoundryChatClient
from labcore.hitl import Decision

GOLD = DATA.parent / "evals" / "gold"
TEST = {c["case_id"]: c for c in json.loads((GOLD / "test_cases.json").read_text())}
OOD = {c["case_id"]: c for c in json.loads((GOLD / "ood_cases.json").read_text())}


async def test_scan_to_review_packet_with_cited_cases():
    desk = ResearchDesk()
    res = await desk.triage(TEST["TES-009"])
    p = res.pending
    assert p.banner == BANNER and p.hypotheses[0]["label"] == "diabetic_retinopathy"
    assert set(p.report["cited_case_ids"]) <= set(p.similar_case_ids)
    assert p.report["cited_reference_ids"]


async def test_reader_override_goes_to_research_log_not_ehr():
    desk = ResearchDesk()
    res = await desk.triage(TEST["TES-008"])
    out = (
        await desk.decide(
            res.run_id, res.request_id, Decision(True, "dr-okafor", overrides={"final_label": "normal"})
        )
    ).output
    assert out["final_label"] == "normal" and out["ehr_written"] is False
    assert desk.research_log[-1]["reviewer"] == "dr-okafor"


async def test_every_ood_scan_is_denied_before_reasoning():
    desk = ResearchDesk()
    for c in OOD.values():
        res = await desk.triage(c)
        assert res.pending is None
        assert res.output["status"] == "denied_out_of_distribution" and res.output["hypotheses"] == []
        assert "reason" not in res.output["trail"]


async def test_malformed_packet_is_denied():
    desk = ResearchDesk()
    bad = {**TEST["TES-001"], "image": [[0.1, 0.2], [0.3]]}
    res = await desk.triage(bad)
    assert res.output["status"] == "denied_out_of_distribution"


async def test_explainer_citing_unknown_case_is_rejected():
    def liar(_m, opts):
        if opts.get("response_format") is not None:
            txt = json.dumps(
                {
                    "banner": BANNER,
                    "summary": "x",
                    "findings": [],
                    "cited_case_ids": ["LIB-999"],
                    "cited_reference_ids": [],
                    "limitations": "",
                }
            )
            return ChatResponse(messages=[Message(role="assistant", contents=[txt])])
        return None

    desk = ResearchDesk(writer_client=MockFoundryChatClient(script=liar))
    res = await desk.triage(TEST["TES-001"])
    assert "LIB-999" not in res.pending.report["cited_case_ids"]
    assert any("not retrieved" in i for i in res.pending.issues)


async def test_explainer_without_banner_is_rejected():
    def no_banner(_m, opts):
        if opts.get("response_format") is not None:
            txt = json.dumps(
                {
                    "banner": "",
                    "summary": "Diagnosis: glaucoma",
                    "findings": [],
                    "cited_case_ids": ["LIB-001"],
                    "cited_reference_ids": [],
                    "limitations": "",
                }
            )
            return ChatResponse(messages=[Message(role="assistant", contents=[txt])])
        return None

    desk = ResearchDesk(writer_client=MockFoundryChatClient(script=no_banner))
    res = await desk.triage(TEST["TES-001"])
    assert res.pending.report["banner"] == BANNER


async def test_ehr_write_tool_is_deny_listed():
    from agent_framework import Agent

    from labcore.middleware import deny_tools

    written = []

    @tool
    def ehr_write_observation(query: str) -> str:
        """Would write to a health record."""
        written.append(query)
        return "ok"

    agent = Agent(
        client=MockFoundryChatClient(), tools=[ehr_write_observation], middleware=[deny_tools(DENIED)]
    )
    assert "DENIED" in (await agent.run("write it")).text and written == []


async def test_report_renders_feature_contributions():
    desk = ResearchDesk()
    p = (await desk.triage(TEST["TES-009"])).pending
    lines = p.report["feature_contributions"]
    assert lines and all("(ablation)" in x or "(shap_kernel)" in x for x in lines)
    # diabetic retinopathy should lean on specks / dark dots, not on the cup ratio
    assert any(k in " ".join(lines) for k in ("specks", "dark_dots"))
    assert not any(x.startswith("cup_ratio") for x in lines)
