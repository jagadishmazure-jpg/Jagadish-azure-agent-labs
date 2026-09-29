"""Risk scoring, geospatial exposure and the emergency decision-support packet.

Risk (0-100) = posterior probability x exposure factor, where exposure comes from the Azure Maps
stand-in (population, facilities). The decision-support output lists options for the duty officer;
it is advice for a person, never an automatic action."""

from __future__ import annotations

from signal_fusion.models import HAZARDS

LEVELS = ((20, "low"), (45, "elevated"), (70, "high"), (101, "severe"))
EXPOSED_BY_HAZARD = {
    "flood": {"hospital", "shelter", "dam", "hazmat", "school"},
    "quake": {"hospital", "school", "bridge", "dam", "hazmat"},
    "tsunami": {"hospital", "hazmat", "shelter"},
}
PLAYBOOK = {
    "flood": [
        "Ask the dam operator for spillway status and planned releases",
        "Pre-position pumps and sandbags near the listed facilities",
        "Check shelter capacity with the local authority",
    ],
    "quake": [
        "Request structural checks for listed hospitals, schools and bridges",
        "Put search-and-rescue teams on standby",
        "Watch for aftershocks in the next seismic window",
    ],
    "tsunami": [
        "Contact the national tsunami warning centre to confirm the tide-gauge trend",
        "Prepare, but do not issue, a coastal warning draft for the authorised warning officer",
        "Check the port fuel terminal shutdown procedure",
    ],
}


def level_of(score: float) -> str:
    return next(name for bound, name in LEVELS if score < bound)


def score(fusion: dict, place: dict) -> dict:
    factor = 0.6 + 0.4 * place["exposure"]
    per = {h: round(100 * fusion["posterior"][h] * factor, 1) for h in HAZARDS}
    primary = max(per, key=lambda h: per[h])
    top = per[primary]
    return {
        "scores": per,
        "levels": {h: level_of(s) for h, s in per.items()},
        "primary_hazard": primary if top >= LEVELS[0][0] else "none",
        "level": level_of(top),
        "exposure_factor": round(factor, 3),
    }


def affected(place: dict, hazard: str) -> list[str]:
    if hazard == "none":
        return []
    return [f["id"] for f in place["facilities"] if f["category"] in EXPOSED_BY_HAZARD[hazard]]


def decision_support(risk: dict, place: dict, fusion: dict) -> dict:
    hz, lv = risk["primary_hazard"], risk["level"]
    proposed = "recommend_warning_review" if lv in {"high", "severe"} else "monitor"
    return {
        "proposed": proposed,
        "options": PLAYBOOK.get(hz, ["Keep monitoring; no action proposed"])
        if lv != "low"
        else ["Keep monitoring"],
        "affected_facilities": affected(place, hz),
        "neighbours_to_watch": [n for n, _ in place["neighbours"]] if lv in {"high", "severe"} else [],
        "uncertainty": fusion["uncertainty"].get(hz, 0.0) if hz != "none" else 0.0,
        "note": "Advice for the duty officer. The lab has no alert channel and sends nothing to the public.",
    }
