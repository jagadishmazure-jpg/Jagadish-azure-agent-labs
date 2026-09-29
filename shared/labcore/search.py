"""Azure AI Search stand-in: an in-memory index with keyword (BM25-style), vector (cosine) and
hybrid (reciprocal rank fusion) queries plus equality filters. Deterministic, so evals are stable.
`AzureSearchStub` marks where `azure.search.documents.SearchClient` would go."""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from labcore.config import AzureStub

_TOKEN = re.compile(r"[a-z0-9]+")


def tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def hash_embed(text: str, dim: int = 64) -> list[float]:
    """Feature-hashing text embedding (stand-in for an embeddings deployment)."""
    v = [0.0] * dim
    for t in tokens(text):
        h = int(hashlib.sha1(t.encode()).hexdigest(), 16)
        v[h % dim] += 1.0 if (h >> 8) & 1 else -1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def cosine(a: list[float], b: list[float]) -> float:
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return sum(x * y for x, y in zip(a, b, strict=True)) / (na * nb)


@dataclass
class Hit:
    id: str
    score: float
    doc: dict[str, Any]
    keyword_rank: int | None = None
    vector_rank: int | None = None
    similarity: float = 0.0


@dataclass
class HybridIndexStandIn:
    name: str
    docs: dict[str, dict[str, Any]] = field(default_factory=dict)
    k1: float = 1.2
    b: float = 0.75

    def upsert(self, doc: dict[str, Any]) -> None:
        """doc needs `id`; optional `text` (keyword field) and `vector`."""
        self.docs[doc["id"]] = doc

    def _filtered(self, flt: dict[str, Any] | None) -> list[dict[str, Any]]:
        return [d for d in self.docs.values() if all(d.get(k) == v for k, v in (flt or {}).items())]

    def _bm25(self, query: str, pool: list[dict[str, Any]]) -> list[tuple[str, float]]:
        q = tokens(query)
        if not q or not pool:
            return []
        toks = {d["id"]: tokens(d.get("text", "")) for d in pool}
        avg = sum(len(t) for t in toks.values()) / len(toks) or 1.0
        df = Counter(t for ts in toks.values() for t in set(ts))
        n = len(pool)
        scored = []
        for did, ts in toks.items():
            tf = Counter(ts)
            s = 0.0
            for t in q:
                if tf[t]:
                    idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                    s += (
                        idf
                        * tf[t]
                        * (self.k1 + 1)
                        / (tf[t] + self.k1 * (1 - self.b + self.b * len(ts) / avg))
                    )
            if s > 0:
                scored.append((did, s))
        return sorted(scored, key=lambda x: (-x[1], x[0]))

    def search(
        self,
        text: str = "",
        vector: list[float] | None = None,
        *,
        top: int = 5,
        filter: dict[str, Any] | None = None,
        rrf_k: int = 60,
    ) -> list[Hit]:
        pool = self._filtered(filter)
        kw = self._bm25(text, pool) if text else []
        vec: list[tuple[str, float]] = []
        if vector is not None:
            vec = sorted(
                ((d["id"], cosine(vector, d["vector"])) for d in pool if "vector" in d),
                key=lambda x: (-x[1], x[0]),
            )
        fused: dict[str, float] = {}
        kw_rank = {d: i + 1 for i, (d, _) in enumerate(kw)}
        vec_rank = {d: i + 1 for i, (d, _) in enumerate(vec)}
        sims = dict(vec)
        for ranks in (kw_rank, vec_rank):
            for d, r in ranks.items():
                fused[d] = fused.get(d, 0.0) + 1.0 / (rrf_k + r)
        order = sorted(fused.items(), key=lambda x: (-x[1], x[0]))[:top]
        return [Hit(d, s, self.docs[d], kw_rank.get(d), vec_rank.get(d), sims.get(d, 0.0)) for d, s in order]


class AzureSearchStub(AzureStub):
    service = "azure-ai-search"


class CosmosContainerStub(AzureStub):
    service = "cosmos-db"
