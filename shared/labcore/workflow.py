"""Helpers around MAF workflows: a node base class with a step budget and a span per node, and a
runner that returns either the final output or the pending human-review request."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent_framework import Executor, Workflow

from labcore.tracing import span


class StepBudgetExceeded(RuntimeError):
    pass


@dataclass
class RunState:
    """Mutable state object passed along a lab's graph (subclassed per lab)."""

    run_id: str
    steps: int = 0
    max_steps: int = 30
    trail: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    def step(self, node: str) -> None:
        self.steps += 1
        self.trail.append(node)
        if self.steps > self.max_steps:
            raise StepBudgetExceeded(f"{node}: step budget {self.max_steps} exceeded")


class LabNode(Executor):
    """Executor base: counts a step and opens a span. Subclasses call `self.enter(state)`."""

    node = "node"

    def __init__(self, id: str | None = None, **deps: Any) -> None:
        super().__init__(id=id or self.node)
        self.deps = deps

    def enter(self, state: RunState):
        state.step(self.node)
        return span(f"node.{self.node}", run=state.run_id, step=state.steps)


@dataclass
class RunResult:
    outputs: list[Any]
    pending: Any | None  # the request payload awaiting a human
    request_id: str | None

    @property
    def output(self) -> Any:
        return self.outputs[-1] if self.outputs else None


def summarize(result) -> RunResult:
    outputs = list(result.get_outputs())
    pending = result.get_request_info_events()
    if pending:
        return RunResult(outputs, pending[0].data, pending[0].request_id)
    return RunResult(outputs, None, None)


async def start(wf: Workflow, message: Any) -> RunResult:
    return summarize(await wf.run(message))


async def respond(wf: Workflow, request_id: str, answer: Any) -> RunResult:
    return summarize(await wf.run(responses={request_id: answer}))
