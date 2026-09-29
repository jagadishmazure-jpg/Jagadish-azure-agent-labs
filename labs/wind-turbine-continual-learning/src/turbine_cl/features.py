"""Physics-informed residual features: what the turbine does minus what a healthy turbine would do
at the same wind and ambient temperature. The detector and the episode signatures both use these."""

from __future__ import annotations

import numpy as np

RATED_KW = 2000.0
FEATURES = (
    "power_residual_pct",
    "rpm_residual",
    "gearbox_residual_c",
    "generator_residual_c",
    "vibration_residual",
    "pitch_residual_deg",
    "ambient_c",
)


def expected(row: dict) -> dict:
    w = row["wind_ms"]
    p = RATED_KW * min(1.0, max(0.0, ((w - 3) / 9) ** 3))
    return {
        "power": p,
        "rpm": min(16.0, max(6.0, 6 + w * 0.9)),
        "gearbox": 55 + 15 * p / RATED_KW + (row["ambient_c"] - 10) * 0.5,
        "generator": 60 + 20 * p / RATED_KW,
        "vibration": 2.0 + 0.1 * w,
        "pitch": 0.0 if w < 12 else (w - 12) * 2.2,
    }


def residuals(row: dict) -> list[float]:
    e = expected(row)
    return [
        (row["power_kw"] - e["power"]) / max(e["power"], 200.0) * 100,
        row["rotor_rpm"] - e["rpm"],
        row["gearbox_temp_c"] - e["gearbox"],
        row["generator_temp_c"] - e["generator"],
        row["vibration_mm_s"] - e["vibration"],
        row["pitch_deg"] - e["pitch"],
        row["ambient_c"],
    ]


def matrix(rows: list[dict]) -> np.ndarray:
    return np.array([residuals(r) for r in rows], dtype=float)
