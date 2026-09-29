"""Research-desk facade. There is deliberately no EHR / FHIR adapter anywhere in this lab."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from eyescan.explainer import make_writer
from eyescan.knowledge import CaseLibrary
from eyescan.reasoning import Reasoner
from labcore.hitl import Decision
from labcore.workflow import RunResult, respond, start

_LIBRARY: CaseLibrary | None = None
_REASONER: Reasoner | None = None


def shared_models() -> tuple[CaseLibrary, Reasoner]:
    """Library index and calibrated reasoner are built once per process (deterministic)."""
    global _LIBRARY, _REASONER
    if _LIBRARY is None:
        _LIBRARY = CaseLibrary()
        _REASONER = Reasoner(_LIBRARY)
        _REASONER.calibrate()
    return _LIBRARY, _REASONER  # type: ignore[return-value]


@dataclass
class ResearchDesk:
    writer_client: object | None = None
    research_log: list[dict] = field(default_factory=list)
    _runs: dict = field(default_factory=dict)

    async def triage(self, scan: dict) -> RunResult:
        from eyescan.workflow import build_workflow

        lib, reasoner = shared_models()
        run_id = f"eye-{uuid.uuid4().hex[:8]}"
        wf = build_workflow(
            library=lib,
            reasoner=reasoner,
            writer=make_writer(self.writer_client),
            research_log=self.research_log,
        )
        self._runs[run_id] = wf
        res = await start(wf, {"run_id": run_id, "scan": scan})
        res.run_id = run_id  # type: ignore[attr-defined]
        return res

    async def decide(self, run_id: str, request_id: str, d: Decision) -> RunResult:
        return await respond(self._runs[run_id], request_id, d)
