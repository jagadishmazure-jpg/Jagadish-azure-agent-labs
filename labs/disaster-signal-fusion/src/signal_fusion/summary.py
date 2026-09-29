"""The only model-written text in this lab: a situation summary for the ops desk (Foundry, mocked).
Scores, levels and options are computed in code and are not part of the model's output schema."""

from __future__ import annotations

from labcore.foundry import FoundryDeployment, FoundryWriter
from labcore.middleware import deny_tools
from signal_fusion.models import SituationSummary

DEPLOYMENT = FoundryDeployment(
    "dsf-situation-summary", model="gpt-5-mini", data_zone="us", purpose="ops-desk situation summary"
)
DENIED = ("*alert*", "*broadcast*", "*notify_public*", "*siren*")
FORBIDDEN_PHRASES = ("alert has been sent", "evacuate now", "warning issued", "sirens activated")
INSTRUCTIONS = (
    "You write a short situation summary for an emergency operations desk. Use only the facts given. "
    "Do not change any score or level, do not give instructions to the public, and cite the sensor "
    "sources and historical record ids you relied on."
)


def make_writer(client=None) -> FoundryWriter:
    return FoundryWriter(
        "situation-summary",
        INSTRUCTIONS,
        SituationSummary,
        DEPLOYMENT,
        client=client,
        middleware=[deny_tools(DENIED)],
    )


def draft(state) -> dict:
    r, place = state.risk, state.places
    hz = r["primary_hazard"]
    used = sorted(state.fusion["weights"])
    fb = state.fusion["fallbacks"]
    fb_txt = "; ".join(f"{s} via {how}" for s, how in sorted(fb.items())) or "none"
    lead = "No hazard above the low band" if hz == "none" else f"{hz.capitalize()} risk is {r['level']}"
    return {
        "headline": f"{place['name']}: {lead} ({r['scores'].get(hz, max(r['scores'].values()))}/100)",
        "body": (
            f"Signals used: {', '.join(used) or 'none'}. Fallbacks: {fb_txt}. "
            f"Scores: flood {r['scores']['flood']}, quake {r['scores']['quake']}, tsunami {r['scores']['tsunami']}. "
            f"{len(state.analogs)} similar past events were retrieved for context. "
            "A duty officer decides whether any warning goes out."
        ),
        "cited_sources": used,
        "cited_records": [a["record_id"] for a in state.analogs[:3]],
    }


def check_factory(state):
    used = set(state.fusion["weights"])
    analog_ids = {a["record_id"] for a in state.analogs}

    def check(s: SituationSummary) -> list[str]:
        problems = []
        if not set(s.cited_sources) <= used:
            problems.append(f"cites sources not used: {sorted(set(s.cited_sources) - used)}")
        if not set(s.cited_records) <= analog_ids:
            problems.append("cites records that were not retrieved")
        text = f"{s.headline} {s.body}".lower()
        problems += [f"forbidden phrase: {p}" for p in FORBIDDEN_PHRASES if p in text]
        return problems

    return check
