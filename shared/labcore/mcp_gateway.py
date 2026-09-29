"""One path from agents to MCP tool servers: allow-list, deny-list, managed-identity token check,
retries on transient errors, result schema validation and a span per call.

Offline, servers run in-process (`mcp.Client(server)`); the token check simulates what a server
behind Entra ID would enforce (audience + app role per tool)."""

from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass, field
from typing import Any

from mcp import Client
from pydantic import BaseModel

from labcore.identity import MockManagedIdentityCredential
from labcore.middleware import ToolDenied, TransientError, retry_async
from labcore.tracing import span


class ToolCallError(RuntimeError):
    pass


@dataclass
class McpServerRef:
    name: str
    server: Any  # an mcp.server.mcpserver.MCPServer (offline) or a URL (azure, not used here)
    audience: str
    tools: dict[str, str]  # tool -> app role required


@dataclass
class McpGateway:
    credential: MockManagedIdentityCredential
    servers: dict[str, McpServerRef] = field(default_factory=dict)
    deny: tuple[str, ...] = ()
    calls: list[dict[str, Any]] = field(default_factory=list)

    def register(self, ref: McpServerRef) -> McpGateway:
        self.servers[ref.name] = ref
        return self

    def _authorize(self, ref: McpServerRef, tool: str) -> None:
        if any(fnmatch.fnmatch(tool, p) for p in self.deny):
            raise ToolDenied(f"{ref.name}.{tool} is deny-listed")
        if tool not in ref.tools:
            raise ToolDenied(f"{ref.name}.{tool} is not on the server allow-list")
        tok = self.credential.get_token(f"{ref.audience}/.default")
        if tok.audience != ref.audience:
            raise ToolDenied(f"token audience {tok.audience} != {ref.audience}")
        if ref.tools[tool] not in tok.roles:
            raise ToolDenied(f"identity {tok.client_id} lacks role {ref.tools[tool]} for {ref.name}.{tool}")

    async def call(
        self, server: str, tool: str, args: dict[str, Any], *, schema: type[BaseModel] | None = None
    ) -> dict[str, Any]:
        ref = self.servers[server]
        self._authorize(ref, tool)

        async def once() -> dict[str, Any]:
            async with Client(ref.server) as c:
                result = await c.call_tool(tool, args)
            if result.is_error:
                text = " ".join(getattr(x, "text", "") for x in result.content)
                if "TRANSIENT" in text:
                    raise TransientError(f"{server}.{tool}: {text}")
                raise ToolCallError(f"{server}.{tool}: {text}")
            payload = result.structured_content or json.loads(result.content[0].text)
            if isinstance(payload, dict) and set(payload) == {"result"}:
                payload = payload["result"]
            return payload

        with span("mcp.call", server=server, tool=tool):
            payload = await retry_async(once, attempts=3)
        self.calls.append({"server": server, "tool": tool})
        return schema.model_validate(payload).model_dump() if schema else payload
