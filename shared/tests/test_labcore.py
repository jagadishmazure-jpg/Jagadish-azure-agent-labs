"""Tests for the shared layers."""

import pytest
from agent_framework import Agent, tool
from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel

from labcore import tracing
from labcore.config import AdapterNotConfigured, LabSettings, pick
from labcore.evals import Threshold, expected_calibration_error, gate, precision_recall
from labcore.foundry import (
    FoundryDeployment,
    FoundryWriter,
    MockFoundryChatClient,
    ZonePolicy,
    ZoneViolation,
    get_chat_client,
)
from labcore.identity import MockManagedIdentityCredential
from labcore.mcp_gateway import McpGateway, McpServerRef
from labcore.middleware import ToolDenied, TransientError, deny_tools, retry_async, validate_tool_result
from labcore.search import HybridIndexStandIn, hash_embed
from labcore.streams import DataLakeStandIn, EventHubStandIn

DEP = FoundryDeployment("t-writer", data_zone="us")


class Note(BaseModel):
    title: str
    body: str


def test_mode_switch_selects_stub_that_raises():
    s = LabSettings(mode="azure")
    client = get_chat_client(DEP, s)
    with pytest.raises(AdapterNotConfigured):
        client.get_response("hi")
    assert pick(lambda: "offline", lambda: "azure", LabSettings()) == "offline"


def test_bad_mode_rejected(monkeypatch):
    monkeypatch.setenv("LAB_MODE", "prod")
    with pytest.raises(ValueError):
        LabSettings.from_env()


def test_zone_policy_rejects_global_and_other_zone():
    with pytest.raises(ZoneViolation):
        ZonePolicy("us").check(FoundryDeployment("g", sku="GlobalStandard"))
    with pytest.raises(ZoneViolation):
        ZonePolicy("us").check(FoundryDeployment("e", data_zone="eu"))


async def test_writer_retries_transient_then_returns_draft():
    w = FoundryWriter("t", "polish", Note, DEP, client=MockFoundryChatClient(fail_times=2))
    packet, issues = await w.write(facts={}, draft={"title": "a", "body": "b"})
    assert packet == {"title": "a", "body": "b"} and issues == []


async def test_writer_degrades_when_check_fails():
    w = FoundryWriter("t", "polish", Note, DEP)
    packet, issues = await w.write(
        facts={}, draft={"title": "a", "body": "b"}, check=lambda v: ["nope"] if v.title == "a" else []
    )
    assert packet["title"] == "a" and issues and w.degraded == 1


async def test_writer_degrades_when_model_always_throttled():
    w = FoundryWriter("t", "polish", Note, DEP, client=MockFoundryChatClient(fail_times=99))
    packet, issues = await w.write(facts={}, draft={"title": "x", "body": "y"})
    assert packet["body"] == "y" and "unavailable" in issues[0]


async def test_deny_listed_tool_never_runs():
    ran = []

    @tool
    def send_public_alert(query: str) -> str:
        """Broadcast."""
        ran.append(query)
        return "sent"

    audit: list = []
    agent = Agent(
        client=MockFoundryChatClient(), tools=[send_public_alert], middleware=[deny_tools(["*alert*"], audit)]
    )
    resp = await agent.run("go")
    assert ran == [] and "DENIED" in resp.text and audit[0]["tool"] == "send_public_alert"


async def test_tool_result_schema_validation():
    @tool
    def lookup(query: str) -> str:
        """Returns junk."""
        return '{"title": 1}'

    agent = Agent(
        client=MockFoundryChatClient(), tools=[lookup], middleware=[validate_tool_result({"lookup": Note})]
    )
    resp = await agent.run("go")
    assert "REJECTED" in resp.text


async def test_retry_async_gives_up():
    n = {"c": 0}

    async def boom():
        n["c"] += 1
        raise TransientError("x")

    with pytest.raises(TransientError):
        await retry_async(boom, attempts=3)
    assert n["c"] == 3


async def test_mcp_gateway_checks_identity_roles_and_deny_list():
    srv = MCPServer("demo")

    @srv.tool()
    def read_thing(thing_id: str) -> dict:
        """Read."""
        return {"id": thing_id}

    ref = McpServerRef("demo", srv, "api://demo", {"read_thing": "Things.Read", "drop_thing": "Things.Write"})
    no_role = McpGateway(MockManagedIdentityCredential()).register(ref)
    with pytest.raises(ToolDenied):
        await no_role.call("demo", "read_thing", {"thing_id": "1"})
    cred = MockManagedIdentityCredential(role_grants={"api://demo": {"Things.Read", "Things.Write"}})
    gw = McpGateway(cred, deny=("drop_*",)).register(ref)
    assert (await gw.call("demo", "read_thing", {"thing_id": "1"}))["id"] == "1"
    with pytest.raises(ToolDenied):
        await gw.call("demo", "drop_thing", {"thing_id": "1"})
    assert cred.issued == ["api://demo"]


def test_hybrid_search_fuses_keyword_and_vector():
    idx = HybridIndexStandIn("t")
    idx.upsert(
        {"id": "a", "text": "termination for convenience", "vector": hash_embed("termination"), "k": 1}
    )
    idx.upsert({"id": "b", "text": "governing law of delaware", "vector": hash_embed("law"), "k": 2})
    hits = idx.search("termination notice", hash_embed("termination"), top=2)
    assert hits[0].id == "a"
    assert [h.id for h in idx.search("law", filter={"k": 1})] == []


def test_event_hub_checkpoint_replay_and_lake():
    hub = EventHubStandIn("t", partitions=2)
    for i in range(5):
        hub.send({"i": i}, partition_key=f"k{i}")
    first = hub.receive("g")
    hub.checkpoint("g", first[:3])
    assert len(hub.receive("g")) < 5 and len(hub.receive("other")) == 5
    lake = DataLakeStandIn()
    uri = lake.write_json("raw/x/1.json", {"a": 1})
    assert uri.startswith("abfss://raw@") and lake.read_json("raw/x/1.json") == {"a": 1}


def test_eval_helpers():
    assert precision_recall(["a", "b"], ["a", "c"]) == (0.5, 0.5)
    assert expected_calibration_error([0.9, 0.9], [True, True]) == pytest.approx(0.1)
    rep = gate("x", {"m": 0.5}, [Threshold("m", ">=", 0.9), Threshold("z", "<=", 1)])
    assert not rep.passed and len(rep.failures) == 2


def test_spans_are_recorded():
    tracing.configure_tracing()
    tracing.clear_spans()
    with tracing.span("unit", a=1):
        pass
    assert any(s.name == "unit" for s in tracing.finished_spans())
