"""Feature and quality jobs written like Azure Functions Event Hub-triggered handlers.

Each handler receives one raw event body and returns a curated record (or raises `Rejected`).
In Azure these would be `@app.event_hub_message_trigger` functions writing to the curated ADLS zone;
here `FUNCTIONS` is a plain registry the ingest node calls."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from signal_fusion.models import CuratedSignal, RawEvent

FUNCTIONS: dict[str, Callable[[RawEvent], CuratedSignal]] = {}


class Rejected(ValueError):
    pass


def event_hub_trigger(source: str):
    def register(fn: Callable[[RawEvent], CuratedSignal]):
        FUNCTIONS[source] = fn
        return fn

    return register


def _curated(ev: RawEvent, values: dict, flags: list[str]) -> CuratedSignal:
    return CuratedSignal(
        source=ev.source, region_id=ev.region_id, ts=ev.ts, quality=ev.quality, values=values, qc_flags=flags
    )


@event_hub_trigger("seismic")
def seismic_qc(ev: RawEvent) -> CuratedSignal:
    p = ev.payload
    samples = p.get("samples") or []
    if len(samples) < 32:
        raise Rejected("seismogram too short")
    flags = ["clipped"] if max(abs(x) for x in samples) > 1.0 else []
    return _curated(
        ev,
        {k: p[k] for k in ("samples", "scale_um", "sample_hz", "depth_km", "offshore", "distance_km")},
        flags,
    )


@event_hub_trigger("satellite")
def satellite_qc(ev: RawEvent) -> CuratedSignal:
    p = ev.payload
    tiles = [p.get("backscatter"), p.get("interferogram_rad")]
    if any(t is None or len(t) != 10 or any(len(r) != 10 for r in t) for t in tiles):
        raise Rejected("SAR tiles must be 10x10")
    return _curated(ev, dict(p), [])


@event_hub_trigger("weather")
def weather_qc(ev: RawEvent) -> CuratedSignal:
    p = dict(ev.payload)
    if p.get("rain_24h_mm", 0) < 0 or p.get("rain_24h_mm", 0) > 2000:
        raise Rejected("rain gauge out of physical range")
    flags = []
    if p.get("rain_rate_mm_h", 0) * 24 < p.get("rain_24h_mm", 0) * 0.02:
        flags.append("rate_total_mismatch")
    return _curated(ev, p, flags)


@event_hub_trigger("displacement")
def displacement_qc(ev: RawEvent) -> CuratedSignal:
    p = dict(ev.payload)
    if abs(p.get("tide_anomaly_m", 0)) > 30:
        raise Rejected("tide anomaly out of range")
    return _curated(ev, p, [])


def hours_between(a: str, b: str) -> float:
    fa = datetime.fromisoformat(a.replace("Z", "+00:00"))
    fb = datetime.fromisoformat(b.replace("Z", "+00:00"))
    return abs((fb - fa).total_seconds()) / 3600
