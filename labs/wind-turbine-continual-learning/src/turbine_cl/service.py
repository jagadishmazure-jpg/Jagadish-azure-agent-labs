from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from labcore.config import pick
from labcore.hitl import Decision
from labcore.streams import EventHubProducerStub, EventHubStandIn
from labcore.workflow import RunResult, respond, start
from turbine_cl.detector import DetectorRegistry
from turbine_cl.diagnose import make_writer
from turbine_cl.episodes import EpisodeStore
from turbine_cl.lessons import LessonRegistry

_REGISTRY = DetectorRegistry()


@dataclass
class DiagnosticsDesk:
    registry: DetectorRegistry = field(default_factory=lambda: _REGISTRY)
    hub: EventHubStandIn = field(
        default_factory=lambda: pick(lambda: EventHubStandIn("turbine-telemetry"), EventHubProducerStub)
    )
    writer_client: object | None = None
    episodes: EpisodeStore | None = None
    lessons: LessonRegistry = field(default_factory=LessonRegistry)
    lesson_candidates: list[dict] = field(default_factory=list)
    _runs: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.detector = self.registry.load_champion()
        self.episodes = self.episodes or EpisodeStore.seeded(self.detector[0])

    def publish(self, rows: list[dict]) -> None:
        for r in rows:
            self.hub.send(r, partition_key=r["turbine_id"])

    async def check(self, turbine_id: str) -> RunResult:
        from turbine_cl.workflow import build_workflow

        run_id = f"wtg-{uuid.uuid4().hex[:8]}"
        wf = build_workflow(
            hub=self.hub,
            detector=self.detector,
            episodes=self.episodes,
            lessons=self.lessons,
            lesson_candidates=self.lesson_candidates,
            writer=make_writer(self.writer_client),
        )
        self._runs[run_id] = wf
        res = await start(wf, {"run_id": run_id, "turbine_id": turbine_id})
        res.run_id = run_id  # type: ignore[attr-defined]
        return res

    async def decide(self, run_id: str, request_id: str, d: Decision) -> RunResult:
        return await respond(self._runs[run_id], request_id, d)
