"""RAG over the labeled case library and the reference-report notes (AI Search stand-in, hybrid:
keyword over report + metadata words, vector over standardised image features). Also holds the
out-of-distribution gate, which is fitted on the same library."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

import numpy as np

from eyescan import DATA
from eyescan.vision import FEATURES, VisionStandIn, metadata_text
from labcore.search import HybridIndexStandIn


def load(name: str) -> list[dict]:
    return json.loads((DATA / name).read_text())


@dataclass
class CaseLibrary:
    vision: VisionStandIn = field(default_factory=VisionStandIn)
    cases: list[dict] = field(default_factory=lambda: load("library.json"))
    index: HybridIndexStandIn = field(default_factory=lambda: HybridIndexStandIn("eye-cases"))
    refs: HybridIndexStandIn = field(default_factory=lambda: HybridIndexStandIn("eye-references"))
    mu: np.ndarray | None = None
    sd: np.ndarray | None = None
    ood_radius: float = 0.0

    def __post_init__(self) -> None:
        raw = np.array([[self.vision.features(c["image"])[f] for f in FEATURES] for c in self.cases])
        self.mu, self.sd = raw.mean(0), raw.std(0) + 1e-6
        z = (raw - self.mu) / self.sd
        for c, zi in zip(self.cases, z, strict=True):
            self.index.upsert(
                {
                    "id": c["case_id"],
                    "label": c["label"],
                    "vector": zi.tolist(),
                    "z": zi,
                    "text": f"{c['report']} {metadata_text(c['metadata'])}",
                }
            )
        # radius = 1.5x the largest leave-one-out nearest-neighbour distance inside the library
        d = np.linalg.norm(z[:, None, :] - z[None, :, :], axis=-1)
        np.fill_diagonal(d, np.inf)
        self.ood_radius = float(d.min(1).max() * 1.5)
        for r in load("references.json"):
            self.refs.upsert({"id": r["ref_id"], "label": r["label"], "text": r["text"]})

    def embed(self, features: dict[str, float]) -> list[float]:
        v = (np.array([features[f] for f in FEATURES]) - self.mu) / self.sd
        return v.tolist()

    def nearest_distance(self, emb: list[float]) -> float:
        e = np.asarray(emb)
        return float(min(np.linalg.norm(e - d["z"]) for d in self.index.docs.values()))

    def similar(self, emb: list[float], meta: dict, k: int = 5) -> list[dict]:
        e = np.asarray(emb)
        hits = self.index.search(metadata_text(meta), emb, top=k)
        return [
            {
                "case_id": h.id,
                "label": h.doc["label"],
                "similarity": round(h.similarity, 4),
                "distance": round(float(np.linalg.norm(e - h.doc["z"])), 4),
                "rrf": round(h.score, 5),
            }
            for h in hits
        ]

    def references(self, labels: list[str], text: str) -> list[dict]:
        """Best-matching reference note per candidate label (keyword search, label filter)."""
        out = []
        for lab in labels:
            hits = self.refs.search(f"{text} {lab.replace('_', ' ')}", filter={"label": lab}, top=1)
            docs = [h.doc for h in hits] or [d for d in self.refs.docs.values() if d["label"] == lab][:1]
            out += [{"ref_id": d["id"], "label": d["label"], "text": d["text"]} for d in docs]
        return out


@dataclass(frozen=True)
class OodGate:
    """Deny before any reasoning when the scan does not look like the library."""

    allowed_modality: str = "fundus"
    shape: tuple[int, int] = (16, 16)

    def check(self, scan: dict, dist: float, radius: float, feats: dict[str, float]) -> dict:
        reasons = []
        meta = scan["metadata"]
        if meta["modality"] != self.allowed_modality:
            reasons.append(f"modality {meta['modality']} is not {self.allowed_modality}")
        if tuple(meta["shape"]) != self.shape:
            reasons.append("unexpected image size")
        if feats["background_std"] < 1e-3:
            reasons.append("blank or flat image")
        if not math.isfinite(dist) or dist > radius:
            reasons.append(f"far from every library case (distance {dist:.2f} > {radius:.2f})")
        return {
            "denied": bool(reasons),
            "reasons": reasons,
            "distance": round(dist, 3),
            "radius": round(radius, 3),
        }
