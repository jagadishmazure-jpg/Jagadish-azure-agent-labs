"""Diagnosis from similar episodes and a fixed action catalog; Foundry (mocked) writes the
recommendation text, constrained to catalog actions and retrieved episode ids."""

from __future__ import annotations

from pydantic import BaseModel

from labcore.foundry import FoundryDeployment, FoundryWriter
from labcore.middleware import deny_tools

DEPLOYMENT = FoundryDeployment(
    "turbine-diagnosis", model="gpt-5-mini", data_zone="us", purpose="maintenance recommendation"
)
DENIED = ("promote_*", "retrain_*", "*fit_detector*", "*registry*", "*shutdown_fleet*")
CATALOG = {
    "gearbox_bearing": ["borescope_gearbox", "oil_sample", "derate_to_70pct"],
    "pitch_fault": ["inspect_pitch_actuator", "reset_pitch_controller"],
    "generator_overheat": ["inspect_generator_cooling", "derate_to_70pct"],
    "icing": ["enable_blade_heating", "pause_turbine_until_thaw"],
    "sensor_drift": ["recalibrate_gearbox_temp_sensor", "cross_check_with_oil_temperature"],
    "false_alarm": ["no_action"],
    "unknown_pattern": ["schedule_general_inspection"],
}
MIN_SIMILARITY = 0.6
URGENT = {"gearbox_bearing", "generator_overheat"}


class Recommendation(BaseModel):
    turbine_id: str
    diagnosis: str
    urgency: str
    actions: list[str]
    cited_episodes: list[str]
    feature_contributions: list[str] = []
    text: str


def diagnose(similar: list[dict]) -> tuple[str, float]:
    good = [s for s in similar if s["similarity"] >= MIN_SIMILARITY]
    if not good:
        return "unknown_pattern", 0.0
    votes: dict[str, float] = {}
    for s in good:
        votes[s["diagnosis"]] = votes.get(s["diagnosis"], 0.0) + s["similarity"]
    best = max(votes, key=lambda k: votes[k])
    return best, round(votes[best] / sum(votes.values()), 3)


def draft(
    turbine: str,
    diagnosis: str,
    confidence: float,
    similar: list[dict],
    top_features: list[str],
    contributions: dict | None = None,
) -> dict:
    from labcore.explain import render

    return {
        "feature_contributions": render(contributions) if contributions else [],
        "turbine_id": turbine,
        "diagnosis": diagnosis,
        "urgency": "within 24h" if diagnosis in URGENT else "next visit",
        "actions": CATALOG[diagnosis],
        "cited_episodes": [s["episode_id"] for s in similar if s["similarity"] >= MIN_SIMILARITY],
        "text": f"{turbine}: pattern matches {diagnosis.replace('_', ' ')} (confidence {confidence}); "
        f"strongest deviations: {', '.join(top_features)}.",
    }


def make_writer(client=None) -> FoundryWriter:
    return FoundryWriter(
        "turbine-recommendation",
        "Write a short maintenance recommendation for a technician. Only use catalog actions.",
        Recommendation,
        DEPLOYMENT,
        client=client,
        middleware=[deny_tools(DENIED)],
    )


def check_factory(diagnosis: str, similar: list[dict]):
    ids = {s["episode_id"] for s in similar}

    def check(r: Recommendation) -> list[str]:
        p = []
        if not set(r.actions) <= set(CATALOG.get(diagnosis, [])):
            p.append("actions outside the catalog for this diagnosis")
        if not set(r.cited_episodes) <= ids:
            p.append("cites episodes that were not retrieved")
        if r.diagnosis != diagnosis:
            p.append("diagnosis changed by the writer")
        return p

    return check
