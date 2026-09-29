"""Event Hubs and ADLS Gen2 stand-ins shared by the streaming labs.

`EventHubStandIn` keeps partitions, sequence numbers and per-consumer-group checkpoints in memory,
so replaying from a checkpoint behaves like the real service. `DataLakeStandIn` is a path -> bytes
store with the raw/curated zone layout. The Azure versions are stubs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from labcore.config import AzureStub


@dataclass(frozen=True)
class EventData:
    partition: int
    sequence: int
    body: dict[str, Any]
    partition_key: str


@dataclass
class EventHubStandIn:
    name: str
    partitions: int = 4
    _log: dict[int, list[EventData]] = field(default_factory=dict)
    _checkpoints: dict[tuple[str, int], int] = field(default_factory=dict)

    def _partition_for(self, key: str) -> int:
        return int(hashlib.md5(key.encode()).hexdigest(), 16) % self.partitions

    def send(self, body: dict[str, Any], partition_key: str) -> EventData:
        p = self._partition_for(partition_key)
        log = self._log.setdefault(p, [])
        ev = EventData(p, len(log), body, partition_key)
        log.append(ev)
        return ev

    def receive(self, consumer_group: str = "$Default", max_events: int = 10_000) -> list[EventData]:
        """Events after the group's checkpoint, in partition then sequence order."""
        out: list[EventData] = []
        for p in sorted(self._log):
            start = self._checkpoints.get((consumer_group, p), -1) + 1
            out.extend(self._log[p][start:])
        return out[:max_events]

    def checkpoint(self, consumer_group: str, events: list[EventData]) -> None:
        for ev in events:
            key = (consumer_group, ev.partition)
            self._checkpoints[key] = max(self._checkpoints.get(key, -1), ev.sequence)


@dataclass
class DataLakeStandIn:
    account: str = "labsdatalake"
    files: dict[str, bytes] = field(default_factory=dict)

    def write_json(self, path: str, obj: Any) -> str:
        self.files[path] = json.dumps(obj, sort_keys=True, default=str).encode()
        return f"abfss://{path.split('/', 1)[0]}@{self.account}.dfs.core.windows.net/{path.split('/', 1)[-1]}"

    def read_json(self, path: str) -> Any:
        return json.loads(self.files[path])

    def list(self, prefix: str) -> list[str]:
        return sorted(p for p in self.files if p.startswith(prefix))


class EventHubProducerStub(AzureStub):
    service = "event-hubs"


class DataLakeStub(AzureStub):
    service = "adls-gen2"
