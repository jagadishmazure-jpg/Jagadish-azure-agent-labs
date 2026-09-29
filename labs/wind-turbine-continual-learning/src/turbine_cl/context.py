"""Turbine context: fleet model per turbine, maintenance history and weather taken from telemetry."""

from __future__ import annotations

import json

from turbine_cl import DATA


def fleet() -> dict[str, str]:
    return json.loads((DATA / "fleet.json").read_text())


def history(turbine_id: str) -> list[dict]:
    return [
        h
        for h in json.loads((DATA / "maintenance_history.json").read_text())
        if h["turbine_id"] == turbine_id
    ]


def turbine_context(turbine_id: str, rows: list[dict]) -> dict:
    amb = [r["ambient_c"] for r in rows] or [0.0]
    wind = [r["wind_ms"] for r in rows] or [0.0]
    return {
        "turbine_id": turbine_id,
        "turbine_model": fleet().get(turbine_id, "unknown"),
        "ambient_c": round(sum(amb) / len(amb), 1),
        "wind_ms": round(sum(wind) / len(wind), 1),
        "recent_work": history(turbine_id),
    }
