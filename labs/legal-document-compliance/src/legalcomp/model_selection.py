"""Model / tool selection for each capability the lab needs.

The scores below are MOCK numbers for illustration (nothing here was benchmarked against live
services), except rows marked `measured`, which are computed from this lab's own gold set. The
selection rule is the part that matters: best quality that meets the latency and cost ceilings."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Candidate:
    capability: str
    name: str
    quality: float  # task metric in [0, 1]
    p95_latency_s: float
    cost_per_1k_pages_usd: float
    source: str  # "mock" or "measured"


CANDIDATES = [
    Candidate("parsing", "Document Intelligence prebuilt-layout", 0.97, 2.5, 10.0, "mock"),
    Candidate("parsing", "Document Intelligence prebuilt-read", 0.90, 1.2, 1.5, "mock"),
    Candidate("parsing", "open-source OCR + heuristics", 0.78, 4.0, 0.4, "mock"),
    Candidate("ocr_quality", "junk score (confidence + token shape)", 1.00, 0.01, 0.0, "measured"),
    Candidate("ocr_quality", "mean OCR confidence only", 0.83, 0.01, 0.0, "mock"),
    Candidate("reasoning", "gpt-5-mini (DataZoneStandard)", 0.93, 1.8, 3.0, "mock"),
    Candidate("reasoning", "gpt-5 (DataZoneStandard)", 0.96, 6.5, 18.0, "mock"),
    Candidate("reasoning", "small open model (serverless)", 0.81, 1.1, 0.8, "mock"),
    Candidate("legal_understanding", "lexicon rules + gpt-5-mini check", 1.00, 1.9, 3.0, "measured"),
    Candidate("legal_understanding", "lexicon rules only", 1.00, 0.01, 0.0, "measured"),
    Candidate("legal_understanding", "gpt-5-mini zero-shot", 0.88, 1.8, 3.0, "mock"),
]
CEILINGS = {
    "parsing": (3.0, 12.0),
    "ocr_quality": (0.5, 1.0),
    "reasoning": (3.0, 5.0),
    "legal_understanding": (3.0, 5.0),
}


def choose(capability: str) -> Candidate:
    lat, cost = CEILINGS[capability]
    ok = [
        c
        for c in CANDIDATES
        if c.capability == capability and c.p95_latency_s <= lat and c.cost_per_1k_pages_usd <= cost
    ]
    # prefer quality; break ties toward the option with a model check (auditability), then cheaper
    return sorted(ok, key=lambda c: (-c.quality, "check" not in c.name, c.cost_per_1k_pages_usd))[0]


def table() -> str:
    head = "| Capability | Candidate | Quality | p95 latency (s) | Cost / 1k pages (USD) | Source | Chosen |\n|---|---|---|---|---|---|---|\n"
    chosen = {cap: choose(cap).name for cap in CEILINGS}
    return head + "".join(
        f"| {c.capability} | {c.name} | {c.quality:.2f} | {c.p95_latency_s} | {c.cost_per_1k_pages_usd} | {c.source} | "
        f"{'yes' if chosen[c.capability] == c.name else ''} |\n"
        for c in CANDIDATES
    )


if __name__ == "__main__":  # pragma: no cover
    print(table())
