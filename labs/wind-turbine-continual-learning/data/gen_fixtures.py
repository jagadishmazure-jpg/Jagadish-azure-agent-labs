"""Synthetic 10-minute SCADA telemetry for a 2 MW turbine fleet, with four injected fault types.

    python data/gen_fixtures.py

* data/normal_train.json        normal rows the detector is trained on
* data/episodes.json            past, technician-confirmed episodes (the retrieval memory)
* data/stream_scenarios.json    one-hour windows used by the live demo and tests
* data/fleet.json               turbine models and site context
* data/maintenance_history.json recent work orders per turbine
* evals/gold/heldout.json       held-out failure and normal windows for the detector promotion gate
* evals/gold/lesson_eval.json   windows used to gate learned lessons (with turbine context)

Model B turbines have a known failure mode that memory alone gets wrong: a drifting gearbox
temperature sensor that reads ~14 C high while vibration stays normal. It looks like a bearing
problem to pattern matching and to past episodes, but it is a sensor fault."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
GOLD = HERE.parent / "evals" / "gold"
RATED_KW = 2000.0
FAULTS = ("gearbox_bearing", "pitch_fault", "generator_overheat", "icing")


def expected_power(w: np.ndarray) -> np.ndarray:
    return RATED_KW * np.clip(((w - 3) / 9) ** 3, 0, 1)


def rows(
    rng: np.random.Generator, n: int, fault: str | None = None, turbine: str = "WTG-01", t0: int = 0
) -> list[dict]:
    w = rng.uniform(6, 18, n) if fault != "icing" else rng.uniform(7, 12, n)
    amb = rng.uniform(-5, 25, n) if fault != "icing" else rng.uniform(-8, -1, n)
    p = expected_power(w) * (1 + rng.normal(0, 0.03, n))
    rpm = np.clip(6 + w * 0.9, 6, 16) + rng.normal(0, 0.3, n)
    gear = 55 + 15 * p / RATED_KW + (amb - 10) * 0.5 + rng.normal(0, 1.5, n)
    gen = 60 + 20 * p / RATED_KW + rng.normal(0, 2, n)
    vib = 2.0 + 0.1 * w + rng.normal(0, 0.2, n)
    pitch = np.where(w < 12, 0.0, (w - 12) * 2.2) + rng.normal(0, 0.5, n)
    if fault == "gearbox_bearing":
        gear += rng.uniform(12, 18, n)
        vib += rng.uniform(2.5, 4, n)
    elif fault == "pitch_fault":
        pitch = np.full(n, 10.0) + rng.normal(0, 0.3, n)
        p *= 0.6
    elif fault == "generator_overheat":
        gen += rng.uniform(20, 30, n)
        p *= 0.9
    elif fault == "icing":
        p *= 0.65
        vib += 1.0
    elif fault == "sensor_drift":
        gear += rng.uniform(12, 16, n)
    return [
        {
            "turbine_id": turbine,
            "t": t0 + i,
            "wind_ms": round(float(w[i]), 2),
            "power_kw": round(float(p[i]), 1),
            "rotor_rpm": round(float(rpm[i]), 2),
            "gearbox_temp_c": round(float(gear[i]), 2),
            "generator_temp_c": round(float(gen[i]), 2),
            "vibration_mm_s": round(float(vib[i]), 3),
            "pitch_deg": round(float(pitch[i]), 2),
            "ambient_c": round(float(amb[i]), 2),
        }
        for i in range(n)
    ]


def window(rng, fault: str | None, turbine: str, t0: int, n: int = 6) -> dict:
    return {"turbine_id": turbine, "label": fault or "normal", "rows": rows(rng, n, fault, turbine, t0)}


NOTES = {
    "gearbox_bearing": (
        "Bearing wear on the gearbox high-speed shaft",
        ["borescope_gearbox", "oil_sample", "derate_to_70pct"],
    ),
    "pitch_fault": (
        "Pitch actuator stuck on one blade",
        ["inspect_pitch_actuator", "reset_pitch_controller"],
    ),
    "generator_overheat": ("Generator cooling fan failure", ["inspect_generator_cooling", "derate_to_70pct"]),
    "icing": ("Blade icing in freezing fog", ["enable_blade_heating", "pause_turbine_until_thaw"]),
}


FLEET = {f"WTG-{i:02d}": "model-A-2.0MW" for i in range(1, 41)} | {
    f"WTG-{i:02d}": "model-B-2.3MW-cold" for i in range(41, 61)
}


def maintenance_history() -> list[dict]:
    return [
        {"turbine_id": "WTG-07", "date": "2026-06-02", "action": "oil_sample", "result": "normal"},
        {
            "turbine_id": "WTG-44",
            "date": "2026-08-20",
            "action": "borescope_gearbox",
            "result": "no damage found",
        },
        {"turbine_id": "WTG-44", "date": "2026-09-10", "action": "oil_sample", "result": "normal"},
        {
            "turbine_id": "WTG-45",
            "date": "2026-07-15",
            "action": "inspect_generator_cooling",
            "result": "fan replaced",
        },
    ]


if __name__ == "__main__":
    rng = np.random.default_rng(20260929)
    GOLD.mkdir(parents=True, exist_ok=True)
    (HERE / "normal_train.json").write_text(json.dumps(rows(rng, 480)) + "\n")
    eps = []
    for i in range(16):
        f = FAULTS[i % 4]
        w = window(rng, f, f"WTG-{(i % 8) + 1:02d}", 1000 + i * 10)
        note, actions = NOTES[f]
        eps.append(
            {
                "episode_id": f"EP-{2021 + i // 4}-{i:03d}",
                "turbine_id": w["turbine_id"],
                "diagnosis": f,
                "note": note,
                "actions": actions,
                "outcome": "resolved",
                "rows": w["rows"],
            }
        )
    (HERE / "episodes.json").write_text(json.dumps(eps) + "\n")
    scen = {
        name: window(rng, None if name == "normal" else name, "WTG-07", 5000) for name in ("normal", *FAULTS)
    }
    (HERE / "stream_scenarios.json").write_text(json.dumps(scen) + "\n")
    held = [window(rng, f, f"WTG-{k + 10:02d}", 9000 + k * 6) for k, f in enumerate([*FAULTS] * 5)]
    held += [window(rng, None, f"WTG-{k + 30:02d}", 9500 + k * 6) for k in range(20)]
    (GOLD / "heldout.json").write_text(json.dumps(held) + "\n")
    scen2 = {
        "sensor_drift_B": window(rng, "sensor_drift", "WTG-44", 6000),
        "sensor_drift_on_A": window(rng, "sensor_drift", "WTG-07", 6100),
    }
    (HERE / "learning_scenarios.json").write_text(json.dumps(scen2) + "\n")
    lesson = [window(rng, "sensor_drift", f"WTG-{41 + k:02d}", 7000 + k * 6) for k in range(6)]
    lesson += [window(rng, "gearbox_bearing", f"WTG-{50 + k:02d}", 7100 + k * 6) for k in range(5)]
    lesson += [window(rng, "gearbox_bearing", f"WTG-{20 + k:02d}", 7200 + k * 6) for k in range(5)]
    a_drift = [window(rng, "sensor_drift", f"WTG-{30 + k:02d}", 7300 + k * 6) for k in range(4)]
    for w in a_drift:  # on model A the same reading turned out to be early bearing heat
        w["label"] = "gearbox_bearing"
    lesson += a_drift
    for w in lesson:
        w["turbine_model"] = FLEET[w["turbine_id"]]
    (GOLD / "lesson_eval.json").write_text(json.dumps(lesson) + "\n")
    (HERE / "fleet.json").write_text(json.dumps(FLEET, indent=1) + "\n")
    (HERE / "maintenance_history.json").write_text(json.dumps(maintenance_history(), indent=1) + "\n")
    print(f"normal rows 480, episodes {len(eps)}, held-out windows {len(held)}")
