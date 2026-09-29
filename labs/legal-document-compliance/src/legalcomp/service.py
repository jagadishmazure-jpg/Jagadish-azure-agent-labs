from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from labcore.config import pick
from labcore.hitl import Decision
from labcore.search import AzureSearchStub, HybridIndexStandIn
from labcore.workflow import RunResult, respond, start
from legalcomp.classify import make_writer
from legalcomp.mcp_servers import gateway


@dataclass
class ComplianceDesk:
    writer_client: object | None = None
    redo_client: object | None = None
    gw: object = field(default_factory=gateway)
    index: HybridIndexStandIn = field(
        default_factory=lambda: pick(lambda: HybridIndexStandIn("clause-chunks"), AzureSearchStub)
    )
    _runs: dict = field(default_factory=dict)

    async def review(self, doc_id: str) -> RunResult:
        from legalcomp.workflow import build_workflow

        run_id = f"legal-{uuid.uuid4().hex[:8]}"
        wf = build_workflow(
            gateway=self.gw,
            index=self.index,
            writer=make_writer(self.writer_client),
            redo_writer=make_writer(self.redo_client, redo=True),
        )
        self._runs[run_id] = wf
        res = await start(wf, {"run_id": run_id, "doc_id": doc_id})
        res.run_id = run_id  # type: ignore[attr-defined]
        return res

    async def decide(self, run_id: str, request_id: str, d: Decision) -> RunResult:
        return await respond(self._runs[run_id], request_id, d)
