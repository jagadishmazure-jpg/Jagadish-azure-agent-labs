"""Azure Maps stand-in over a local GeoJSON file: region polygons, facility points, point-in-polygon,
neighbours by centroid distance and exposure. `AzureMapsStub` marks the real adapter seam."""

from __future__ import annotations

import itertools
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from labcore.config import AzureStub
from signal_fusion import DATA


def point_in_polygon(lon: float, lat: float, ring: list[list[float]]) -> bool:
    inside = False
    for (x1, y1), (x2, y2) in itertools.pairwise(ring):
        if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


@dataclass
class MapsStandIn:
    path: Path = DATA / "places.geojson"
    regions: dict[str, dict] = field(default_factory=dict)
    facilities: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        fc = json.loads(self.path.read_text())
        for f in fc["features"]:
            p = f["properties"]
            if p["kind"] == "region":
                self.regions[p["region_id"]] = {**p, "ring": f["geometry"]["coordinates"][0]}
            else:
                lon, lat = f["geometry"]["coordinates"]
                self.facilities.append({**p, "lon": lon, "lat": lat})

    def centroid(self, region_id: str) -> tuple[float, float]:
        ring = self.regions[region_id]["ring"][:-1]
        return sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring)

    def region_of(self, lon: float, lat: float) -> str | None:
        return next((r for r, v in self.regions.items() if point_in_polygon(lon, lat, v["ring"])), None)

    def facilities_in(self, region_id: str) -> list[dict]:
        return [f for f in self.facilities if self.region_of(f["lon"], f["lat"]) == region_id]

    def neighbours(self, region_id: str, max_km: float = 30.0) -> list[tuple[str, float]]:
        c = self.centroid(region_id)
        out = [(r, haversine_km(c, self.centroid(r))) for r in self.regions if r != region_id]
        return sorted([(r, round(d, 1)) for r, d in out if d <= max_km], key=lambda x: x[1])

    def context(self, region_id: str) -> dict:
        reg = self.regions[region_id]
        return {
            "region_id": region_id,
            "name": reg["name"],
            "population": reg["population"],
            "coastal": reg["coastal"],
            "elevation_m": reg["elevation_m"],
            "exposure": min(1.0, reg["population"] / 1_000_000),
            "facilities": [
                {"id": f["facility_id"], "name": f["name"], "category": f["category"]}
                for f in self.facilities_in(region_id)
            ],
            "neighbours": self.neighbours(region_id),
        }


class AzureMapsStub(AzureStub):
    service = "azure-maps"
