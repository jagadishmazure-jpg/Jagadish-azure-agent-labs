from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from labcore.hitl import Decision
from labcore.workflow import RunResult, respond, start
from roadgraph.models import PlanRequest
from roadgraph.narrative import make_writer


@dataclass
class PlanningDesk:
    writer_client: object | None = None
    _runs: dict = field(default_factory=dict)

    async def plan(
        self,
        budget_usd: float = 400_000,
        closed_segments: list[str] | None = None,
        what_if: list[str] | None = None,
    ) -> RunResult:
        from roadgraph.workflow import build_workflow

        run_id = f"road-{uuid.uuid4().hex[:8]}"
        runtime: dict = {}
        wf = build_workflow(writer=make_writer(self.writer_client), runtime=runtime)
        self._runs[run_id] = (wf, runtime)
        res = await start(
            wf,
            PlanRequest(
                run_id=run_id,
                budget_usd=budget_usd,
                closed_segments=closed_segments or [],
                what_if=what_if or [],
            ),
        )
        res.run_id = run_id  # type: ignore[attr-defined]
        res.runtime = runtime  # type: ignore[attr-defined]
        return res

    async def decide(self, run_id: str, request_id: str, d: Decision) -> RunResult:
        return await respond(self._runs[run_id][0], request_id, d)
