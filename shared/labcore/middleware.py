"""MAF middleware and harness helpers shared by the labs.

* `deny_tools(...)`: function middleware that blocks deny-listed tools before they run.
* `retry_tool(...)`: function middleware that retries a tool on `TransientError`.
* `validate_tool_result(...)`: function middleware that schema-checks a tool's result.
* `retry_async(...)`: deterministic retry for any awaitable (no sleeps, no jitter, so tests are fast).

Tool output is untrusted until it has passed a schema."""

from __future__ import annotations

import fnmatch
from collections.abc import Awaitable, Callable, Iterable
from typing import Any, TypeVar

from agent_framework import FunctionInvocationContext, function_middleware
from pydantic import BaseModel, ValidationError

from labcore.tracing import span

T = TypeVar("T")


class TransientError(RuntimeError):
    """Retryable failure (throttling, timeouts)."""


class ToolDenied(RuntimeError):
    pass


async def retry_async(
    fn: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    on: tuple[type[BaseException], ...] = (TransientError,),
) -> T:
    last: BaseException | None = None
    for i in range(1, attempts + 1):
        try:
            return await fn()
        except on as exc:
            last = exc
            with span("retry", attempt=i, error=type(exc).__name__):
                pass
    assert last is not None
    raise last


def deny_tools(patterns: Iterable[str], audit: list[dict[str, Any]] | None = None):
    """Glob patterns, e.g. {"ehr_*", "*_public_alert", "promote_*"}."""
    pats = tuple(patterns)

    @function_middleware
    async def _deny(ctx: FunctionInvocationContext, call_next) -> None:
        name = ctx.function.name
        if any(fnmatch.fnmatch(name, p) for p in pats):
            if audit is not None:
                audit.append({"tool": name, "decision": "denied"})
            with span("tool.denied", tool=name):
                ctx.result = f"DENIED: tool '{name}' is on the deny list for this lab"
            return
        await call_next()

    return _deny


def retry_tool(attempts: int = 3):
    @function_middleware
    async def _retry(ctx: FunctionInvocationContext, call_next) -> None:
        for i in range(1, attempts + 1):
            try:
                await call_next()
                return
            except TransientError:
                if i == attempts:
                    raise

    return _retry


def validate_tool_result(schemas: dict[str, type[BaseModel]]):
    @function_middleware
    async def _validate(ctx: FunctionInvocationContext, call_next) -> None:
        await call_next()
        schema = schemas.get(ctx.function.name)
        if schema is None:
            return
        try:
            raw = ctx.result
            schema.model_validate_json(raw) if isinstance(raw, str | bytes) else schema.model_validate(raw)
        except ValidationError as exc:
            ctx.result = f"REJECTED: {ctx.function.name} returned data that failed {schema.__name__}: {exc.error_count()} error(s)"

    return _validate
