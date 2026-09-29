"""Ops-desk facade: publish readings to the Event Hub stand-in, assess a region, record the decision."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field

from labcore.config import pick
from labcore.hitl import Decision
from labcore.streams import DataLakeStandIn, DataLakeStub, EventHubProducerStub, EventHubStandIn
from labcore.workflow import RunResult, respond, start
from signal_fusion import DATA
from signal_fusion.agents import HistoricalPatternAgent
from signal_fusion.geo import MapsStandIn
from signal_fusion.models import FusionRequest
from signal_fusion.summary import make_writer


def scenarios() -> dict[str, list[dict]]:
    return json.loads((DATA / "scenarios.json").read_text())


@dataclass
class OpsDesk:
    hub: EventHubStandIn = field(
        default_factory=lambda: pick(lambda: EventHubStandIn("sensor-signals"), EventHubProducerStub)
    )
    lake: DataLakeStandIn = field(default_factory=lambda: pick(DataLakeStandIn, DataLakeStub))
    maps: MapsStandIn = field(default_factory=MapsStandIn)
    history: HistoricalPatternAgent = field(default_factory=HistoricalPatternAgent)
    writer_client: object | None = None
    _runs: dict = field(default_factory=dict)

    def publish(self, readings: list[dict]) -> None:
        for r in readings:
            self.hub.send(r, partition_key=f"{r.get('region_id')}:{r.get('source')}")

    async def assess(self, region_id: str, run_id: str | None = None) -> RunResult:
        from signal_fusion.workflow import build_workflow

        run_id = run_id or f"dsf-{uuid.uuid4().hex[:8]}"
        wf = build_workflow(
            hub=self.hub,
            lake=self.lake,
            maps=self.maps,
            history=self.history,
            writer=make_writer(self.writer_client),
        )
        self._runs[run_id] = wf
        res = await start(wf, FusionRequest(region_id=region_id, run_id=run_id))
        res.run_id = run_id  # type: ignore[attr-defined]
        return res

    async def decide(self, run_id: str, request_id: str, decision: Decision) -> RunResult:
        return await respond(self._runs[run_id], request_id, decision)
