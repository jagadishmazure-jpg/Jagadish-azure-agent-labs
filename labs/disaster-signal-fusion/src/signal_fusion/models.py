"""Pydantic packets for raw events, curated signals, agent findings and the ops-desk review."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

from labcore.workflow import RunState

Source = Literal["seismic", "weather", "satellite", "displacement"]
SOURCES: tuple[str, ...] = ("seismic", "weather", "satellite", "displacement")
HAZARDS: tuple[str, ...] = ("flood", "quake", "tsunami")


class RawEvent(BaseModel):
    source: Source
    region_id: str
    ts: str
    quality: float = Field(ge=0, le=1)
    payload: dict[str, Any]


class CuratedSignal(BaseModel):
    source: Source
    region_id: str
    ts: str
    quality: float
    values: dict[str, Any]
    qc_flags: list[str] = []


class Finding(BaseModel):
    """What one specialist agent reports: features it derived and log-likelihood evidence per hazard."""

    agent: str
    sources: list[str]
    features: dict[str, Any]
    evidence: dict[str, dict[str, float]]  # hazard -> source -> log-likelihood ratio
    weights: dict[str, float]  # source -> reliability weight in [0, 1]
    fallbacks: dict[str, str] = {}  # source -> "neighbour:<region>" | "prior"
    notes: list[str] = []


class SituationSummary(BaseModel):
    headline: str
    body: str
    cited_sources: list[str]
    cited_records: list[str]


@dataclass
class FusionRequest:
    region_id: str
    run_id: str
    window_end: str = "2026-08-14T12:00:00Z"


@dataclass
class DeskState(RunState):
    region_id: str = ""
    window_end: str = ""
    signals: dict[str, dict] = field(default_factory=dict)  # source -> curated signal (as dict)
    neighbour_signals: dict[str, dict] = field(default_factory=dict)
    findings: dict[str, dict] = field(default_factory=dict)
    analogs: list[dict] = field(default_factory=list)
    fusion: dict[str, Any] = field(default_factory=dict)
    risk: dict[str, Any] = field(default_factory=dict)
    places: dict[str, Any] = field(default_factory=dict)
    support: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)


@dataclass
class AlertReview:
    """The packet the duty officer sees. `proposed` is advice; the lab never sends an alert itself."""

    run_id: str
    region_id: str
    primary_hazard: str
    level: str
    risk: dict[str, Any]
    contributions: dict[str, dict[str, float]]
    fallbacks: dict[str, str]
    uncertainty: dict[str, float]
    analog_ids: list[str]
    affected_facilities: list[str]
    proposed: str
    summary: dict[str, Any]
    decision_support: dict[str, Any]
    issues: list[str] = field(default_factory=list)
