"""Regenerates every synthetic fixture for this lab. Places, sensors and "historical" records are
invented; numbers are chosen to be plausible, not measured.

    python data/gen_fixtures.py

Raw sensor payloads look roughly like what the real feeds carry: a short seismogram (samples plus a
scale in micrometres), 10x10 SAR backscatter and interferogram tiles, a weather-station summary and
GNSS / tide-gauge values."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
GOLD = HERE.parent / "evals" / "gold"
WAVELENGTH_MM = 55.5  # C-band SAR

REGIONS = [
    # id, name, lon0, lat0, population, coastal, elevation_m, priors (flood, quake, tsunami)
    ("harbor-delta", "Harbor Delta", 30.00, 10.00, 820_000, True, 4, (0.08, 0.02, 0.01)),
    ("river-valley", "Kestrel River Valley", 30.20, 10.00, 450_000, False, 35, (0.10, 0.02, 0.0005)),
    ("fault-ridge", "Granite Fault Ridge", 30.40, 10.00, 210_000, False, 420, (0.02, 0.06, 0.0005)),
    ("upland-plateau", "Juniper Upland", 30.20, 10.20, 90_000, False, 900, (0.01, 0.01, 0.0005)),
]
FACILITIES = [
    ("hosp-harbor", "Harbor General Hospital", "hospital", 30.05, 10.05),
    ("shelter-delta", "Delta School Shelter", "shelter", 30.12, 10.08),
    ("port-fuel", "Port Fuel Terminal", "hazmat", 30.02, 10.15),
    ("hosp-valley", "Valley Regional Hospital", "hospital", 30.28, 10.06),
    ("dam-kestrel", "Kestrel Dam", "dam", 30.33, 10.17),
    ("school-ridge", "Ridge Primary School", "school", 30.48, 10.10),
    ("bridge-granite", "Granite Pass Bridge", "bridge", 30.52, 10.04),
]


def _rng(*parts: object) -> np.random.Generator:
    return np.random.default_rng(int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:8], 16))


def square(lon0: float, lat0: float, size: float = 0.2) -> list:
    return [
        [[lon0, lat0], [lon0 + size, lat0], [lon0 + size, lat0 + size], [lon0, lat0 + size], [lon0, lat0]]
    ]


def places() -> dict:
    feats = []
    for rid, name, lon, lat, pop, coastal, elev, pri in REGIONS:
        feats.append(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": square(lon, lat)},
                "properties": {
                    "kind": "region",
                    "region_id": rid,
                    "name": name,
                    "population": pop,
                    "coastal": coastal,
                    "elevation_m": elev,
                    "prior": {"flood": pri[0], "quake": pri[1], "tsunami": pri[2]},
                },
            }
        )
    for fid, name, kind, lon, lat in FACILITIES:
        feats.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {"kind": "facility", "facility_id": fid, "name": name, "category": kind},
            }
        )
    return {"type": "FeatureCollection", "features": feats}


# ----------------------------------------------------------------------------- raw payload renderers
def seismogram(key: str, magnitude: float, distance_km: float, n: int = 64) -> dict:
    """Peak amplitude from the Hutton-Boore local-magnitude relation, inverted."""
    log_a = magnitude - 1.11 * math.log10(distance_km) - 0.00189 * distance_km + 2.09
    rng = _rng("seis", key)
    t = np.arange(n)
    onset = 20
    env = np.where(t >= onset, np.exp(-(t - onset) / 12.0), 0.0)
    wave = env * np.sin(t * 1.3) + rng.normal(0, 0.01, n)
    wave = wave / np.max(np.abs(wave))
    return {"samples": [round(float(x), 4) for x in wave], "scale_um": round(10**log_a, 3), "sample_hz": 1.0}


def sar_tiles(key: str, water_pct: float, ground_disp_mm: float) -> dict:
    rng = _rng("sar", key)
    n_water = round(water_pct)  # 100 pixels
    back = np.full(100, 0.62) + rng.normal(0, 0.03, 100)
    back[rng.permutation(100)[:n_water]] = 0.09
    phase = np.full(100, ground_disp_mm * 4 * math.pi / WAVELENGTH_MM) + rng.normal(0, 0.01, 100)
    return {
        "backscatter": [[round(float(x), 3) for x in back[i * 10 : i * 10 + 10]] for i in range(10)],
        "interferogram_rad": [[round(float(x), 4) for x in phase[i * 10 : i * 10 + 10]] for i in range(10)],
        "wavelength_mm": WAVELENGTH_MM,
    }


CALM = {
    "seismic": {"magnitude": 2.1, "depth_km": 12.0, "offshore": False, "distance_km": 80.0},
    "weather": {"rain_24h_mm": 4.0, "rain_rate_mm_h": 0.5, "wind_ms": 5.0, "soil_moisture_pct": 22.0},
    "satellite": {"water_extent_pct": 1.0, "ground_disp_mm": 0.3},
    "displacement": {"gnss_uplift_mm": 0.4, "tide_anomaly_m": 0.02},
}
T = "2026-08-14T06:00:00Z"


def raw(source: str, region: str, key: str, vals: dict, t: str = T, q: float = 0.95) -> dict:
    if source == "seismic":
        payload = {
            **seismogram(key, vals["magnitude"], vals["distance_km"]),
            "depth_km": vals["depth_km"],
            "offshore": vals["offshore"],
            "distance_km": vals["distance_km"],
        }
    elif source == "satellite":
        payload = sar_tiles(key, vals["water_extent_pct"], vals["ground_disp_mm"])
    else:
        payload = dict(vals)
    return {"source": source, "region_id": region, "ts": t, "quality": q, "payload": payload}


def readings(region: str, key: str, drop: tuple[str, ...] = (), t: str = T, **over: dict) -> list[dict]:
    return [
        raw(s, region, f"{key}:{s}", {**v, **over.get(s, {})}, t) for s, v in CALM.items() if s not in drop
    ]


def scenarios() -> dict:
    return {
        "quiet-day": readings("river-valley", "quiet"),
        "monsoon-flood": readings(
            "river-valley",
            "monsoon",
            weather={"rain_24h_mm": 240.0, "rain_rate_mm_h": 38.0, "soil_moisture_pct": 48.0},
            satellite={"water_extent_pct": 21.0},
        ),
        "rain-only": readings(
            "river-valley", "rainonly", weather={"rain_24h_mm": 210.0, "rain_rate_mm_h": 30.0}
        ),
        "offshore-quake": readings(
            "harbor-delta",
            "offshore",
            seismic={"magnitude": 7.8, "depth_km": 18.0, "offshore": True, "distance_km": 90.0},
            displacement={"tide_anomaly_m": 0.9, "gnss_uplift_mm": 35.0},
        ),
        "ridge-quake": readings(
            "fault-ridge",
            "ridge",
            seismic={"magnitude": 6.6, "depth_km": 9.0, "offshore": False, "distance_km": 8.0},
            displacement={"gnss_uplift_mm": 42.0},
            satellite={"ground_disp_mm": 24.0},
        ),
        "flood-satellite-outage": [
            *readings(
                "river-valley",
                "outage",
                drop=("satellite",),
                weather={"rain_24h_mm": 230.0, "rain_rate_mm_h": 35.0, "soil_moisture_pct": 40.0},
            ),
            raw("satellite", "harbor-delta", "outage:nb", {"water_extent_pct": 16.0, "ground_disp_mm": 0.2}),
        ],
    }


def replay() -> list[dict]:
    """Held-out 'historical' events (not in the RAG corpus) with the level the desk judged right."""
    ev = [
        (
            "replay-2019-monsoon",
            "river-valley",
            "flood",
            "severe",
            {
                "weather": {"rain_24h_mm": 260.0, "rain_rate_mm_h": 41.0, "soil_moisture_pct": 50.0},
                "satellite": {"water_extent_pct": 24.0},
            },
            (),
        ),
        (
            "replay-2020-flash",
            "harbor-delta",
            "flood",
            "high",
            {
                "weather": {"rain_24h_mm": 120.0, "rain_rate_mm_h": 25.0},
                "satellite": {"water_extent_pct": 8.0},
            },
            (),
        ),
        (
            "replay-2021-ridge",
            "fault-ridge",
            "quake",
            "high",
            {
                "seismic": {"magnitude": 6.3, "depth_km": 11.0, "distance_km": 10.0},
                "displacement": {"gnss_uplift_mm": 30.0},
                "satellite": {"ground_disp_mm": 18.0},
            },
            (),
        ),
        (
            "replay-2022-megathrust",
            "harbor-delta",
            "tsunami",
            "severe",
            {
                "seismic": {"magnitude": 8.1, "depth_km": 22.0, "offshore": True, "distance_km": 120.0},
                "displacement": {"tide_anomaly_m": 1.2},
            },
            (),
        ),
        (
            "replay-2023-drizzle",
            "upland-plateau",
            "none",
            "low",
            {"weather": {"rain_24h_mm": 30.0, "rain_rate_mm_h": 4.0}},
            (),
        ),
        (
            "replay-2023-deep-quake",
            "fault-ridge",
            "none",
            "low",
            {"seismic": {"magnitude": 5.2, "depth_km": 180.0, "distance_km": 60.0}},
            (),
        ),
        (
            "replay-2024-sat-gap",
            "river-valley",
            "flood",
            "severe",
            {"weather": {"rain_24h_mm": 220.0, "rain_rate_mm_h": 34.0, "soil_moisture_pct": 45.0}},
            ("satellite",),
        ),
        (
            "replay-2025-offshore-small",
            "harbor-delta",
            "none",
            "low",
            {"seismic": {"magnitude": 5.9, "depth_km": 35.0, "offshore": True, "distance_km": 150.0}},
            (),
        ),
    ]
    return [
        {
            "event_id": e,
            "region_id": r,
            "observed_hazard": h,
            "observed_level": lv,
            "readings": readings(r, e, drop=d, **o),
        }
        for e, r, h, lv, o, d in ev
    ]


def archive() -> list[dict]:
    """Fifty years (1975-2024) of invented disaster records for the Historical Pattern Agent's RAG."""
    rng = _rng("archive")
    templates = {
        "flood": (
            "{n} mm of rain in a day over {r}; rivers overtopped and {w}% of the area was under water. "
            "Outcome: {lv} flooding, {d} displaced."
        ),
        "quake": (
            "Magnitude {m} earthquake at {k} km depth near {r}; ground moved {g} mm. "
            "Outcome: {lv} shaking damage, {d} displaced."
        ),
        "tsunami": (
            "Offshore magnitude {m} earthquake; tide gauges rose {t} m along {r}. "
            "Outcome: {lv} coastal inundation, {d} displaced."
        ),
    }
    out = []
    for year in range(1975, 2025):
        for _ in range(2):
            rid, name, *_rest, coastal, _elev, _pri = REGIONS[int(rng.integers(0, 4))]
            hazards = ["flood", "quake"] + (["tsunami"] if coastal else [])
            hz = hazards[int(rng.integers(0, len(hazards)))]
            sev = float(rng.uniform(0, 1))
            lv = "low" if sev < 0.35 else "elevated" if sev < 0.6 else "high" if sev < 0.85 else "severe"
            d = int(sev**2 * 40000)
            text = templates[hz].format(
                n=int(40 + sev * 240),
                r=name,
                w=int(1 + sev * 25),
                lv=lv,
                d=d,
                m=round(4.8 + sev * 3.4, 1),
                k=int(8 + (1 - sev) * 120),
                g=int(sev * 45),
                t=round(0.1 + sev * 1.3, 2),
            )
            out.append(
                {
                    "record_id": f"HIST-{year}-{len(out):03d}",
                    "year": year,
                    "region_id": rid,
                    "hazard": hz,
                    "severity": round(sev, 3),
                    "level": lv,
                    "text": text,
                }
            )
    return out


def signal_usage() -> list[dict]:
    return [
        {
            "case_id": "use-rain",
            "scenario": "rain-only",
            "region_id": "river-valley",
            "hazard": "flood",
            "must_use": ["weather"],
        },
        {
            "case_id": "use-rain-and-sar",
            "scenario": "monsoon-flood",
            "region_id": "river-valley",
            "hazard": "flood",
            "must_use": ["weather", "satellite"],
        },
        {
            "case_id": "use-seismic-gnss-insar",
            "scenario": "ridge-quake",
            "region_id": "fault-ridge",
            "hazard": "quake",
            "must_use": ["seismic", "displacement", "satellite"],
        },
        {
            "case_id": "use-tide-gauge",
            "scenario": "offshore-quake",
            "region_id": "harbor-delta",
            "hazard": "tsunami",
            "must_use": ["seismic", "displacement"],
        },
        {
            "case_id": "neighbour-fallback",
            "scenario": "flood-satellite-outage",
            "region_id": "river-valley",
            "hazard": "flood",
            "must_use": ["weather", "satellite"],
        },
    ]


def dump_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


if __name__ == "__main__":
    GOLD.mkdir(parents=True, exist_ok=True)
    (HERE / "places.geojson").write_text(json.dumps(places(), indent=1) + "\n")
    (HERE / "scenarios.json").write_text(json.dumps(scenarios()) + "\n")
    dump_jsonl(HERE / "history_archive.jsonl", archive())
    dump_jsonl(GOLD / "replay.jsonl", replay())
    dump_jsonl(GOLD / "signal_usage.jsonl", signal_usage())
    print("fixtures written")
