"""Graph work done by the agents, in flow order (topology -> paths -> priority -> impact):

* build_graph      - Graph Engineering Agent: OSM-style nodes/ways + condition, maintenance records and
                     incidents merged onto edges; weights are travel minutes
* features         - Graph Features Agent: shortest paths, demand-weighted usage, edge betweenness
                     centrality, cut edges and the trips each cut edge serves
* priority         - Maintenance Priority Agent: condition need x (usage, centrality, connectivity)
* closure_impact   - Road Closure Impact Agent: remove a segment, reroute every trip, report the
                     extra vehicle-minutes, stranded trips, affected segments and critical reroutes
* road_health      - network-level road health report"""

from __future__ import annotations

import itertools
import json
import math
from pathlib import Path

import networkx as nx

from roadgraph import DATA


def _load(name: str):
    return json.loads((DATA / name).read_text())


def haversine_m(a: dict, b: dict) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(h))


def build_graph(osm: dict | None = None, defects: list[dict] | None = None) -> nx.Graph:
    osm = osm or _load("city_osm.json")
    defects = defects or _load("defects.json")
    records = {r["segment_id"]: r for r in _load("maintenance_records.json")}
    incident_count: dict[str, int] = {}
    for i in _load("incidents.json"):
        incident_count[i["segment_id"]] = incident_count.get(i["segment_id"], 0) + 1
    g = nx.Graph()
    nodes = {n["id"]: n for n in osm["nodes"]}
    for nid, n in nodes.items():
        g.add_node(nid, lat=n["lat"], lon=n["lon"], **n["tags"])
    cond = {d["segment_id"]: d for d in defects}
    for w in osm["ways"]:
        for a, b in zip(w["nodes"], w["nodes"][1:], strict=False):
            length = haversine_m(nodes[a], nodes[b])
            speed = float(w["tags"].get("maxspeed", 30))
            g.add_edge(
                a,
                b,
                id=w["id"],
                length_m=round(length, 1),
                minutes=length / (speed / 3.6) / 60,
                highway=w["tags"]["highway"],
                bridge=w["tags"].get("bridge") == "yes",
                name=w["tags"].get("name", ""),
                incidents=incident_count.get(w["id"], 0),
                last_resurfaced=records.get(w["id"], {}).get("last_resurfaced", 2015),
                failed_patches=records.get(w["id"], {}).get("failed_patches", 0),
                **{k: v for k, v in cond.get(w["id"], {}).items() if k != "segment_id"},
            )
    return g


def edge_by_id(g: nx.Graph, seg: str) -> tuple[str, str]:
    return next((u, v) for u, v, d in g.edges(data=True) if d["id"] == seg)


def demand() -> list[dict]:
    return _load("demand.json")


def trip_minutes(g: nx.Graph, dem: list[dict]) -> list[float | None]:
    out: list[float | None] = []
    for d in dem:
        try:
            out.append(d["trips"] * nx.shortest_path_length(g, d["origin"], d["dest"], weight="minutes"))
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            out.append(None)
    return out


def usage(g: nx.Graph, dem: list[dict]) -> dict[str, float]:
    """Trips per day routed over each segment on shortest paths (critical trips count double)."""
    load = {d["id"]: 0.0 for _, _, d in g.edges(data=True)}
    for d in dem:
        path = nx.shortest_path(g, d["origin"], d["dest"], weight="minutes")
        for a, b in itertools.pairwise(path):
            load[g.edges[a, b]["id"]] += d["trips"] * (2 if d["critical"] else 1)
    return load


def features(g: nx.Graph, dem: list[dict]) -> dict[str, dict]:
    """Per-segment graph features used as context by the priority agent."""
    load = usage(g, dem)
    crit_load = usage(g, [d for d in dem if d["critical"]])
    btw = nx.edge_betweenness_centrality(g, weight="minutes", normalized=True)
    cut = {frozenset(e) for e in nx.bridges(g)}
    out = {}
    for a, b, d in g.edges(data=True):
        served = 0
        if frozenset((a, b)) in cut:
            h = g.copy()
            h.remove_edge(a, b)
            side = nx.node_connected_component(h, a)
            served = sum(x["trips"] for x in dem if (x["origin"] in side) != (x["dest"] in side))
        out[d["id"]] = {
            "usage": load[d["id"]],
            "critical_usage": crit_load[d["id"]],
            "betweenness": round(btw.get((a, b), btw.get((b, a), 0.0)), 4),
            "cut_edge": frozenset((a, b)) in cut,
            "trips_served_if_cut": served,
        }
    return out


def affected_segments(g: nx.Graph, h: nx.Graph, dem: list[dict]) -> list[str]:
    before, after = usage(g, dem), usage_safe(h, dem)
    return sorted(s for s, v in after.items() if v > before.get(s, 0) + 1e-9)


def usage_safe(g: nx.Graph, dem: list[dict]) -> dict[str, float]:
    return usage(g, [d for d in dem if nx.has_path(g, d["origin"], d["dest"])])


def closure_impact(g: nx.Graph, seg: str, dem: list[dict], base: list[float | None] | None = None) -> dict:
    base = base if base is not None else trip_minutes(g, dem)
    h = g.copy()
    h.remove_edge(*edge_by_id(g, seg))
    closed = trip_minutes(h, dem)
    extra = sum(c - b for c, b in zip(closed, base, strict=True) if c is not None and b is not None)
    stranded = [d for d, c in zip(dem, closed, strict=True) if c is None]
    reroutes = []
    for d in dem:
        if d["critical"] and nx.has_path(h, d["origin"], d["dest"]):
            old = nx.shortest_path(g, d["origin"], d["dest"], weight="minutes")
            new = nx.shortest_path(h, d["origin"], d["dest"], weight="minutes")
            if old != new:
                reroutes.append({"origin": d["origin"], "dest": d["dest"], "new_path": new})
    return {
        "segment_id": seg,
        "affected_segments": affected_segments(g, h, dem),
        "critical_reroutes": reroutes,
        "extra_vehicle_minutes": round(extra, 1),
        "stranded_trips": sum(d["trips"] for d in stranded),
        "disconnected": not nx.is_connected(h),
        "hospital_access_lost": any(d["dest"] == "E2" for d in stranded),
        "critical_trips_stranded": sum(d["trips"] for d in stranded if d["critical"]),
    }


def need(d: dict, year: int = 2026) -> float:
    """Condition need from pavement index, potholes, age since resurfacing, failed patches, incidents."""
    base = (100 - d["pci"]) / 100 * (1 + min(d["potholes"], 30) / 30)
    age = min(1.0, max(0, year - d["last_resurfaced"]) / 20)
    return base * (1 + 0.2 * age + 0.05 * d["failed_patches"] + 0.05 * min(d["incidents"], 3))


def priority(g: nx.Graph, feats: dict[str, dict]) -> list[dict]:
    """need x (0.15 + 0.45*usage + 0.40*criticality); criticality mixes critical-trip usage, betweenness
    centrality and the trips a cut edge serves. A busy bridge can therefore outrank a pothole-ridden
    dead end, which pure pothole counting would get wrong."""
    mx = {
        k: max(f[k] for f in feats.values()) or 1.0
        for k in ("usage", "critical_usage", "betweenness", "trips_served_if_cut")
    }
    rows = []
    for _, _, d in g.edges(data=True):
        seg, f = d["id"], feats[d["id"]]
        n = need(d)
        u = f["usage"] / mx["usage"]
        crit = min(
            1.0,
            0.6 * f["critical_usage"] / mx["critical_usage"]
            + 0.25 * f["betweenness"] / mx["betweenness"]
            + 0.15 * f["trips_served_if_cut"] / mx["trips_served_if_cut"],
        )
        rows.append(
            {
                "segment_id": seg,
                "score": round(n * (0.15 + 0.45 * u + 0.40 * crit), 4),
                "need": round(n, 3),
                "usage": round(u, 3),
                "criticality": round(crit, 3),
                "betweenness": f["betweenness"],
                "cut_edge": f["cut_edge"],
                "potholes": d["potholes"],
                "pci": d["pci"],
                "incidents": d["incidents"],
                "cost_usd": d["repair_cost_usd"],
                "days": d["repair_days"],
                "bridge": d["bridge"],
                "name": d["name"],
            }
        )
    return sorted(rows, key=lambda r: (-r["score"], r["segment_id"]))


def road_health(g: nx.Graph, feats: dict[str, dict]) -> dict:
    pcis = [d["pci"] for _, _, d in g.edges(data=True)]
    bands = {"good (>=70)": 0, "fair (50-69)": 0, "poor (<50)": 0}
    for p in pcis:
        bands["good (>=70)" if p >= 70 else "fair (50-69)" if p >= 50 else "poor (<50)"] += 1
    return {
        "segments": len(pcis),
        "mean_pci": round(sum(pcis) / len(pcis), 1),
        "condition_bands": bands,
        "cut_edges": sorted(s for s, f in feats.items() if f["cut_edge"]),
        "river_crossings": sorted(d["id"] for _, _, d in g.edges(data=True) if d["bridge"]),
        "segments_with_incidents": sorted(d["id"] for _, _, d in g.edges(data=True) if d["incidents"]),
        "most_central": sorted(feats, key=lambda s: -feats[s]["betweenness"])[:3],
    }


def load_path(p: str | Path) -> dict:
    return json.loads(Path(p).read_text())
