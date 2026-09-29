"""Clause chunks into the AI Search stand-in (hybrid: keyword + hashed-embedding vector)."""

from __future__ import annotations

from labcore.search import HybridIndexStandIn, hash_embed

MAX_WORDS = 40


def chunk(text: str, n: int = MAX_WORDS) -> list[str]:
    words = text.split()
    return [" ".join(words[i : i + n]) for i in range(0, len(words), n)] or [""]


def index_clauses(index: HybridIndexStandIn, doc_id: str, domain: str, clauses: list[dict]) -> int:
    count = 0
    for c in clauses:
        for i, piece in enumerate(chunk(f"{c['heading']}. {c['text']}")):
            index.upsert(
                {
                    "id": f"{c['clause_id']}#{i}",
                    "clause_id": c["clause_id"],
                    "doc_id": doc_id,
                    "domain": domain,
                    "label": c.get("label", ""),
                    "text": piece,
                    "vector": hash_embed(piece),
                }
            )
            count += 1
    return count
