"""Episode memory: Cosmos DB (vector search) / AI Search stand-in. Past technician-confirmed episodes
are retrieved by signature similarity; new episodes are written only after a technician decision."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from labcore.search import HybridIndexStandIn
from turbine_cl import DATA
from turbine_cl.features import matrix


@dataclass
class EpisodeStore:
    index: HybridIndexStandIn = field(default_factory=lambda: HybridIndexStandIn("turbine-episodes"))
    written: list[dict] = field(default_factory=list)

    @classmethod
    def seeded(cls, det) -> EpisodeStore:
        store = cls()
        for e in json.loads((DATA / "episodes.json").read_text()):
            z = det.z(matrix(e["rows"]))
            f = det.flags(matrix(e["rows"]))
            sig = (z[f] if f.any() else z).mean(0).tolist()
            store.index.upsert(
                {
                    "id": e["episode_id"],
                    "turbine_id": e["turbine_id"],
                    "diagnosis": e["diagnosis"],
                    "actions": e["actions"],
                    "text": e["note"],
                    "vector": sig,
                    "source": "seed",
                }
            )
        return store

    def similar(self, signature: list[float], top: int = 5) -> list[dict]:
        hits = self.index.search(vector=signature, top=top)
        return [
            {
                "episode_id": h.id,
                "diagnosis": h.doc["diagnosis"],
                "similarity": round(h.similarity, 3),
                "actions": h.doc["actions"],
                "turbine_model": h.doc.get("turbine_model"),
            }
            for h in hits
        ]

    def write(self, episode: dict) -> None:
        if not episode.get("confirmed_by"):
            raise ValueError("episodes are only written with a named technician")
        self.index.upsert(
            {
                **episode,
                "id": episode["episode_id"],
                "vector": episode["signature"],
                "text": episode.get("note", ""),
                "source": "technician",
            }
        )
        self.written.append(episode)
