"""Small, deterministic demos of the shared layer, used as the "Real output" of docs/components.

Run `python scripts/component_demos.py <section>`; sections: config, mcp, middleware, foundry,
search, streams, evals, workflow. Offline only; nothing touches Azure."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

os.environ.setdefault("LAB_MODE", "offline")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared"))

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
from labcore.middleware import ToolDenied, deny_tools, validate_tool_result
from labcore.search import HybridIndexStandIn, hash_embed
from labcore.streams import DataLakeStandIn, EventHubStandIn
from labcore.workflow import RunState, StepBudgetExceeded


class Note(BaseModel):
    title: str
    body: str


def config() -> None:
    print("offline pick ->", pick(lambda: "in-memory stand-in", lambda: "azure adapter", LabSettings()))
    client = get_chat_client(FoundryDeployment("writer"), LabSettings(mode="azure"))
    print("azure-mode client ->", type(client).__name__)
    try:
        client.get_response("hello")
    except AdapterNotConfigured as exc:
        print("first use ->", str(exc).split(":")[0], "raises AdapterNotConfigured")
    try:
        os.environ["LAB_MODE"] = "prod"
        LabSettings.from_env()
    except ValueError as exc:
        print("LAB_MODE=prod ->", exc)
    finally:
        os.environ["LAB_MODE"] = "offline"


async def mcp() -> None:
    srv = MCPServer("assets")

    @srv.tool()
    def read_asset(asset_id: str) -> dict:
        """Read one asset."""
        return {"id": asset_id, "status": "in service"}

    ref = McpServerRef(
        "assets", srv, "api://assets", {"read_asset": "Assets.Read", "retire_asset": "Assets.Write"}
    )
    for label, grants, deny in [
        ("no role granted", {}, ()),
        ("read role granted", {"api://assets": {"Assets.Read"}}, ("retire_*",)),
    ]:
        gw = McpGateway(MockManagedIdentityCredential(role_grants=grants), deny=deny).register(ref)
        for tool_name, args in [("read_asset", {"asset_id": "A-7"}), ("retire_asset", {"asset_id": "A-7"})]:
            try:
                print(f"{label}: {tool_name} ->", await gw.call("assets", tool_name, args))
            except ToolDenied as exc:
                print(f"{label}: {tool_name} -> denied: {exc}")


async def middleware() -> None:
    ran: list[str] = []

    @tool
    def send_public_alert(query: str) -> str:
        """Broadcast to the public."""
        ran.append(query)
        return "sent"

    @tool
    def lookup(query: str) -> str:
        """Returns a malformed record."""
        return '{"title": 1}'

    audit: list = []
    a = Agent(
        client=MockFoundryChatClient(), tools=[send_public_alert], middleware=[deny_tools(["*alert*"], audit)]
    )
    print(
        "deny_tools ->", (await a.run("flood at gauge 4")).text, "| tool ran:", bool(ran), "| audit:", audit
    )
    b = Agent(
        client=MockFoundryChatClient(), tools=[lookup], middleware=[validate_tool_result({"lookup": Note})]
    )
    print("validate_tool_result ->", (await b.run("find it")).text)


async def foundry() -> None:
    for d in [FoundryDeployment("w-global", sku="GlobalStandard"), FoundryDeployment("w-eu", data_zone="eu")]:
        try:
            ZonePolicy("us").check(d)
        except ZoneViolation as exc:
            print("ZonePolicy ->", exc)
    dep = FoundryDeployment("w-us")
    draft = {"title": "Crew dispatch", "body": "Send crew 3 to segment R-12."}
    for label, client in [
        ("2 throttles then success", MockFoundryChatClient(fail_times=2)),
        ("always throttled", MockFoundryChatClient(fail_times=99)),
    ]:
        w = FoundryWriter("dispatch", "Polish the draft.", Note, dep, client=client)
        packet, issues = await w.write(facts={"segment": "R-12"}, draft=draft)
        print(f"FoundryWriter ({label}) -> packet == draft: {packet == draft}, issues: {issues}")


def search() -> None:
    idx = HybridIndexStandIn("clauses")
    docs = [
        ("c1", "termination for convenience with 30 days notice", "msa"),
        ("c2", "governing law and venue", "msa"),
        ("c3", "termination for cause after uncured breach", "nda"),
    ]
    for did, text, kind in docs:
        idx.upsert({"id": did, "text": text, "vector": hash_embed(text), "kind": kind})
    for label, kw in [("hybrid", {}), ("hybrid, filter kind=msa", {"filter": {"kind": "msa"}})]:
        hits = idx.search("termination notice", hash_embed("termination notice"), top=3, **kw)
        print(label)
        for h in hits:
            print(f"  {h.id}  rrf={h.score:.4f}  keyword_rank={h.keyword_rank}  vector_rank={h.vector_rank}")


def streams() -> None:
    hub = EventHubStandIn("telemetry", partitions=2)
    for i in range(6):
        hub.send({"reading": i}, partition_key=f"turbine-{i % 3}")
    first = hub.receive("scorer")
    print("first read:", len(first), "events")
    hub.checkpoint("scorer", first[:4])
    print(
        "after checkpoint of 4:",
        len(hub.receive("scorer")),
        "left for 'scorer',",
        len(hub.receive("audit")),
        "for 'audit'",
    )
    lake = DataLakeStandIn()
    print("lake write ->", lake.write_json("raw/telemetry/batch-1.json", {"n": len(first)}))


def evals() -> None:
    print("precision, recall:", precision_recall(["a", "b", "c"], ["a", "c", "d"]))
    print("ECE:", round(expected_calibration_error([0.9, 0.8, 0.6, 0.3], [True, True, False, False]), 4))
    rep = gate(
        "demo", {"recall": 0.82, "ece": 0.04}, [Threshold("recall", ">=", 0.9), Threshold("ece", "<=", 0.1)]
    )
    print("gate:", rep.to_dict())


def workflow() -> None:
    tracing.configure_tracing()
    tracing.clear_spans()
    state = RunState("run-1", max_steps=3)
    try:
        for node in ["ingest", "score", "audit", "redo"]:
            state.step(node)
            with tracing.span(f"node.{node}", run=state.run_id, step=state.steps):
                pass
    except StepBudgetExceeded as exc:
        print("budget ->", exc)
    print("trail:", state.trail)
    print("spans:", [s.name for s in tracing.finished_spans()])


SECTIONS = {
    "config": config,
    "mcp": mcp,
    "middleware": middleware,
    "foundry": foundry,
    "search": search,
    "streams": streams,
    "evals": evals,
    "workflow": workflow,
}

if __name__ == "__main__":
    for name in sys.argv[1:] or list(SECTIONS):
        fn = SECTIONS[name]
        result = fn()
        if asyncio.iscoroutine(result):
            asyncio.run(result)
