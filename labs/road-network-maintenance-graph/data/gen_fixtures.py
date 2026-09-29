"""Synthetic OSM-style city ("Millbrook") for the road maintenance lab. No map download needed.

Layout: a 4x4 street grid west of the river, a small east district with the hospital reached over
two bridges, and a residential cul-de-sac with bad pavement but very little traffic.

    python data/gen_fixtures.py

`evals/gold/closures.jsonl` holds invented "historical closures": the extra vehicle-minutes per day
a traffic study measured, simulated here as the shortest-path detour plus deterministic +-10% noise."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import networkx as nx

HERE = Path(__file__).parent
GOLD = HERE.parent / "evals" / "gold"

BLOCK_LAT, BLOCK_LON = 0.0018, 0.0022  # ~200 m


def nodes() -> list[dict]:
    out = []
    for r in range(4):
        for c in range(4):
            out.append(
                {"id": f"W{r}{c}", "lat": 45.0 + r * BLOCK_LAT, "lon": 7.0 + c * BLOCK_LON, "tags": {}}
            )
    for i, (r, c) in enumerate([(1, 5), (2, 5), (2, 6), (3, 5)]):
        out.append({"id": f"E{i}", "lat": 45.0 + r * BLOCK_LAT, "lon": 7.0 + c * BLOCK_LON, "tags": {}})
    out += [
        {"id": "C1", "lat": 45.0 - BLOCK_LAT, "lon": 7.0, "tags": {}},
        {"id": "C2", "lat": 45.0 - 2 * BLOCK_LAT, "lon": 7.0, "tags": {}},
    ]
    tags = {
        "W00": {"amenity": "fire_station"},
        "E2": {"amenity": "hospital"},
        "W21": {"amenity": "school"},
        "W12": {"shop": "market"},
    }
    for n in out:
        n["tags"].update(tags.get(n["id"], {}))
    return out


def ways() -> list[dict]:
    w = []

    def add(a: str, b: str, highway: str, speed: int, **extra) -> None:
        w.append(
            {
                "id": f"w-{a}-{b}",
                "nodes": [a, b],
                "tags": {"highway": highway, "maxspeed": speed, **{k: str(v) for k, v in extra.items()}},
            }
        )

    for r in range(4):
        for c in range(3):
            add(f"W{r}{c}", f"W{r}{c + 1}", "primary" if r == 1 else "residential", 50 if r == 1 else 30)
    for c in range(4):
        for r in range(3):
            add(f"W{r}{c}", f"W{r + 1}{c}", "secondary" if c == 0 else "residential", 40 if c == 0 else 30)
    add("W13", "E0", "primary", 50, bridge="yes", name="North Bridge")
    add("W33", "E3", "secondary", 40, bridge="yes", name="South Bridge")
    add("E0", "E1", "primary", 50)
    add("E1", "E2", "primary", 40)
    add("E1", "E3", "residential", 30)
    add("W00", "C1", "residential", 30, name="Quarry Lane")
    add("C1", "C2", "residential", 30, name="Quarry Lane")
    return w


def defects() -> list[dict]:
    """Pavement condition (PCI 0-100), pothole count, repair cost and duration per segment."""
    special = {
        "w-C1-C2": (22, 31, 38_000, 3),  # cul-de-sac: worst potholes in town, almost no traffic
        "w-W00-C1": (35, 18, 42_000, 3),
        "w-W13-E0": (48, 6, 160_000, 10),  # North Bridge deck: few potholes, carries the hospital route
        "w-W11-W12": (51, 9, 55_000, 4),
        "w-W12-W13": (55, 8, 58_000, 4),
        "w-W33-E3": (63, 4, 140_000, 9),
        "w-E0-E1": (58, 7, 60_000, 4),
        "w-W02-W03": (40, 14, 36_000, 2),
    }
    out = []
    for w in ways():
        h = int(hashlib.md5(w["id"].encode()).hexdigest()[:6], 16)
        pci, pot, cost, days = special.get(w["id"], (70 + h % 25, h % 4, 25_000 + (h % 5) * 5_000, 2))
        out.append(
            {"segment_id": w["id"], "pci": pci, "potholes": pot, "repair_cost_usd": cost, "repair_days": days}
        )
    return out


def demand() -> list[dict]:
    """Daily trips between node pairs. Hospital and fire-station trips are flagged critical."""
    trips = []
    homes = ["W30", "W31", "W32", "W20", "W22", "W33", "C2", "C1"]
    for h in homes:
        trips.append(
            {"origin": h, "dest": "E2", "trips": 350 if h not in {"C1", "C2"} else 12, "critical": True}
        )
        trips.append(
            {"origin": h, "dest": "W12", "trips": 500 if h not in {"C1", "C2"} else 15, "critical": False}
        )
    for dst in ["E2", "E3", "W33", "C2", "W03"]:
        trips.append({"origin": "W00", "dest": dst, "trips": 20, "critical": True})
    trips += [
        {"origin": "W10", "dest": "E1", "trips": 900, "critical": False},
        {"origin": "W03", "dest": "E3", "trips": 400, "critical": False},
        {"origin": "W21", "dest": "W02", "trips": 300, "critical": False},
    ]
    return trips


def haversine_m(a: dict, b: dict) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(h))


def graph() -> nx.Graph:
    g = nx.Graph()
    pos = {n["id"]: n for n in nodes()}
    for w in ways():
        a, b = w["nodes"]
        g.add_edge(a, b, id=w["id"], minutes=haversine_m(pos[a], pos[b]) / (w["tags"]["maxspeed"] / 3.6) / 60)
    for n in pos:
        g.nodes[n]["pos"] = pos[n]
    return g


def trip_minutes(g: nx.Graph) -> dict[int, float | None]:
    out: dict[int, float | None] = {}
    for i, d in enumerate(demand()):
        try:
            out[i] = d["trips"] * nx.shortest_path_length(g, d["origin"], d["dest"], weight="minutes")
        except nx.NetworkXNoPath:
            out[i] = None
    return out


def closures() -> list[dict]:
    g = graph()
    base = trip_minutes(g)
    dem = demand()
    out = []
    for seg, year in [
        ("w-W13-E0", 2019),
        ("w-W33-E3", 2020),
        ("w-C1-C2", 2021),
        ("w-W11-W12", 2022),
        ("w-W00-C1", 2023),
        ("w-E0-E1", 2024),
        ("w-W02-W03", 2024),
    ]:
        h = g.copy()
        a, b = next((u, v) for u, v, d in g.edges(data=True) if d["id"] == seg)
        h.remove_edge(a, b)
        closed = trip_minutes(h)
        extra = sum(closed[i] - base[i] for i in base if closed[i] is not None and base[i] is not None)
        stranded = sum(dem[i]["trips"] for i in closed if closed[i] is None)
        noise = 1 + ((int(hashlib.md5(seg.encode()).hexdigest()[:4], 16) % 21) - 10) / 100
        out.append(
            {
                "closure_id": f"CL-{year}-{seg}",
                "segment_id": seg,
                "year": year,
                "observed_extra_vehicle_minutes": round(extra * noise, 1),
                "observed_stranded_trips": stranded,
                "observed_disconnected": not nx.is_connected(h),
                "observed_hospital_access_lost": any(
                    closed[i] is None and dem[i]["dest"] == "E2" for i in closed
                ),
            }
        )
    return out


def maintenance_records() -> list[dict]:
    """Past work per segment: last resurfacing year and how many patch jobs failed since."""
    out = []
    for w in ways():
        h = int(hashlib.md5(("m" + w["id"]).encode()).hexdigest()[:6], 16)
        last = 2008 + h % 15
        fails = h % 3
        if w["id"] in {"w-W13-E0", "w-C1-C2"}:
            last, fails = 2009, 3
        out.append({"segment_id": w["id"], "last_resurfaced": last, "failed_patches": fails})
    return out


def incidents() -> list[dict]:
    """Closures and incidents logged by the city (invented)."""
    return [
        {
            "incident_id": "INC-2023-014",
            "segment_id": "w-W13-E0",
            "type": "deck joint failure",
            "year": 2023,
            "closure_hours": 36,
        },
        {
            "incident_id": "INC-2024-002",
            "segment_id": "w-W11-W12",
            "type": "crash",
            "year": 2024,
            "closure_hours": 4,
        },
        {
            "incident_id": "INC-2024-019",
            "segment_id": "w-E0-E1",
            "type": "water main break",
            "year": 2024,
            "closure_hours": 20,
        },
        {
            "incident_id": "INC-2025-007",
            "segment_id": "w-C1-C2",
            "type": "pothole damage claim",
            "year": 2025,
            "closure_hours": 0,
        },
        {
            "incident_id": "INC-2025-011",
            "segment_id": "w-W33-E3",
            "type": "flooding",
            "year": 2025,
            "closure_hours": 12,
        },
    ]


def routes() -> list[dict]:
    """Optimal travel time for a few origin-destination pairs (route-quality gold)."""
    g = graph()
    out = []
    for o, d in [("W30", "E2"), ("W00", "E3"), ("C2", "W12"), ("W03", "E3"), ("W10", "E1")]:
        out.append(
            {"origin": o, "dest": d, "minutes": round(nx.shortest_path_length(g, o, d, weight="minutes"), 3)}
        )
    return out


def pairwise() -> list[dict]:
    """Ranking expectations a planner would sign off: connectivity beats raw pothole count."""
    return [
        {"higher": "w-W13-E0", "lower": "w-C1-C2", "why": "hospital route bridge vs low-traffic cul-de-sac"},
        {"higher": "w-W11-W12", "lower": "w-W00-C1", "why": "busy arterial vs cul-de-sac access"},
        {"higher": "w-W13-E0", "lower": "w-W02-W03", "why": "bridge vs quiet residential block"},
    ]


def dump(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


if __name__ == "__main__":
    GOLD.mkdir(parents=True, exist_ok=True)
    (HERE / "city_osm.json").write_text(json.dumps({"nodes": nodes(), "ways": ways()}, indent=1) + "\n")
    (HERE / "defects.json").write_text(json.dumps(defects(), indent=1) + "\n")
    (HERE / "demand.json").write_text(json.dumps(demand(), indent=1) + "\n")
    dump(GOLD / "closures.jsonl", closures())
    dump(GOLD / "pairwise.jsonl", pairwise())
    dump(GOLD / "routes.jsonl", routes())
    (HERE / "maintenance_records.json").write_text(json.dumps(maintenance_records(), indent=1) + "\n")
    (HERE / "incidents.json").write_text(json.dumps(incidents(), indent=1) + "\n")
    (GOLD / "must_fix.json").write_text(
        json.dumps({"budget_usd": 400000, "segments": ["w-W13-E0", "w-W11-W12"]}) + "\n"
    )
    print("fixtures written")
