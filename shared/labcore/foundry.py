"""Azure AI Foundry access, mocked.

* `FoundryDeployment` describes a model deployment and the data zone it must be served from
  ("in-zone": DataZoneStandard deployments keep prompts and completions inside the US or EU zone).
* `ZonePolicy` refuses a deployment that is outside the lab's zone or uses the Global SKU.
* `MockFoundryChatClient` is a real MAF `BaseChatClient`, so `Agent`, tools, middleware and
  structured output behave as they would against Foundry, but the answers are deterministic.
* `FoundryWriter` is the only way the labs let a model touch output: it polishes a draft that code
  already computed, the result is schema-validated, and a failed or invalid answer falls back to the
  draft (a degraded but still valid packet)."""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from agent_framework import Agent, BaseChatClient, ChatResponse, Content, Message
from agent_framework._tools import FunctionInvocationLayer
from pydantic import BaseModel, ValidationError

from labcore.config import AzureStub, LabSettings, settings
from labcore.middleware import TransientError, retry_async
from labcore.tracing import span

Script = Callable[[list[Message], dict[str, Any]], ChatResponse | None]


@dataclass(frozen=True)
class FoundryDeployment:
    name: str
    model: str = "gpt-5-mini"
    sku: str = "DataZoneStandard"
    data_zone: str = "us"
    purpose: str = ""


class ZoneViolation(RuntimeError):
    pass


@dataclass(frozen=True)
class ZonePolicy:
    data_zone: str = "us"
    allowed_skus: frozenset[str] = frozenset({"DataZoneStandard", "DataZoneProvisionedManaged"})

    def check(self, d: FoundryDeployment) -> FoundryDeployment:
        if d.sku not in self.allowed_skus:
            raise ZoneViolation(f"{d.name}: sku {d.sku} may process data outside the {self.data_zone} zone")
        if d.data_zone != self.data_zone:
            raise ZoneViolation(f"{d.name}: deployment zone {d.data_zone} != required {self.data_zone}")
        return d


def _json_block(text: str) -> dict | None:
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


class MockFoundryChatClient(FunctionInvocationLayer, BaseChatClient):
    """Deterministic stand-in for a Foundry chat deployment.

    1. `script` hook may return a full response (tests use it to simulate bad model output).
    2. The first `fail_times` calls raise `TransientError` (a 429 stand-in) to exercise retries.
    3. Tools offered and none called yet -> call the first tool with {"query": <user text>}.
    4. `response_format` requested and the prompt carries a ```json {"draft": ...}``` block -> return
       the draft verbatim (facts come from code; the model only rewords).
    5. Otherwise echo the last tool result or a short mock reply."""

    OTEL_PROVIDER_NAME = "mock-foundry"

    def __init__(self, script: Script | None = None, fail_times: int = 0, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.script = script
        self.fail_times = fail_times
        self.calls = 0

    async def _inner_get_response(self, *, messages, stream, options, **kwargs):  # type: ignore[override]
        self.calls += 1
        if self.calls <= self.fail_times:
            raise TransientError("mock 429: deployment throttled")
        msgs = list(messages)
        if self.script is not None:
            scripted = self.script(msgs, dict(options))
            if scripted is not None:
                return scripted
        results = [c for m in msgs for c in m.contents if c.type == "function_result"]
        tools = options.get("tools") or []
        user = next((m.text for m in reversed(msgs) if m.role == "user"), "")
        if tools and not results:
            name = getattr(tools[0], "name", "tool")
            call = Content.from_function_call(uuid.uuid4().hex[:8], name, arguments={"query": user[:200]})
            return ChatResponse(messages=[Message(role="assistant", contents=[call])])
        payload = _json_block(user) or {}
        if options.get("response_format") is not None and "draft" in payload:
            text = json.dumps(payload["draft"])
        elif results:
            text = str(results[-1].result)
        else:
            text = f"[mock-foundry] {user[:300]}"
        return ChatResponse(messages=[Message(role="assistant", contents=[text])], model="mock-deterministic")


class FoundryChatClientStub(AzureStub):
    """Where `agent_framework_foundry.FoundryChatClient` would be constructed with managed identity."""

    service = "foundry"


def get_chat_client(deployment: FoundryDeployment, s: LabSettings | None = None) -> BaseChatClient:
    s = s or settings()
    ZonePolicy(s.data_zone).check(deployment)
    if s.azure:
        return FoundryChatClientStub(endpoint=s.foundry_project_endpoint, model=deployment.name)  # type: ignore[return-value]
    return MockFoundryChatClient()


@dataclass
class FoundryWriter:
    """Structured writing agent: draft in, schema-valid packet out."""

    role: str
    instructions: str
    schema: type[BaseModel]
    deployment: FoundryDeployment
    client: BaseChatClient | None = None
    middleware: list = field(default_factory=list)
    attempts: int = 3
    degraded: int = 0

    def __post_init__(self) -> None:
        self.client = self.client or get_chat_client(self.deployment)
        self.agent = Agent(
            client=self.client,
            name=f"{self.role}-writer",
            instructions=self.instructions,
            description=f"{self.role} writer on {self.deployment.name} ({self.deployment.data_zone} zone)",
            middleware=self.middleware or None,
        )

    async def write(
        self,
        *,
        facts: dict[str, Any],
        draft: dict[str, Any],
        check: Callable[[BaseModel], list[str]] | None = None,
    ) -> tuple[dict[str, Any], list[str]]:
        """Returns (packet, issues). Issues are non-empty only when the draft fallback was used."""
        prompt = (
            f"Use only these facts. Return JSON for {self.schema.__name__}.\n"
            f"```json\n{json.dumps({'facts': facts, 'draft': draft}, default=str)}\n```"
        )
        issues: list[str] = []
        with span("foundry.write", role=self.role, deployment=self.deployment.name):
            try:
                resp = await retry_async(
                    lambda: self.agent.run(prompt, options={"response_format": self.schema}),
                    attempts=self.attempts,
                )
                value = resp.value
                if value is None:
                    value = self.schema.model_validate_json(resp.text)
                problems = check(value) if check else []
                if not problems:
                    return value.model_dump(), []
                issues = [f"{self.role}: model output rejected: {p}" for p in problems]
            except (TransientError, ValidationError, ValueError) as exc:
                issues = [f"{self.role}: model unavailable or invalid ({type(exc).__name__})"]
        self.degraded += 1
        return self.schema.model_validate(draft).model_dump(), issues
