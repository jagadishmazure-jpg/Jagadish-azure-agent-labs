from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from labcore.workflow import RunState


@dataclass
class PlanRequest:
    run_id: str
    budget_usd: float = 400_000
    closed_segments: list[str] = field(default_factory=list)  # segments already closed (e.g. flooding)
    what_if: list[str] = field(default_factory=list)  # extra closures to simulate for the report


@dataclass
class PlanState(RunState):
    budget_usd: float = 0.0
    closed_segments: list[str] = field(default_factory=list)
    what_if: list[str] = field(default_factory=list)
    next: str = "graph_engineering"
    done: list[str] = field(default_factory=list)
    graph_summary: dict[str, Any] = field(default_factory=dict)
    features: dict[str, dict] = field(default_factory=dict)
    health: dict[str, Any] = field(default_factory=dict)
    impacts: dict[str, dict] = field(default_factory=dict)
    ranked: list[dict] = field(default_factory=list)
    plan: dict[str, Any] = field(default_factory=dict)
    narrative: dict[str, Any] = field(default_factory=dict)


@dataclass
class EngineerReview:
    run_id: str
    plan: dict[str, Any]
    narrative: dict[str, Any]
    top_ranked: list[dict]
    closure_impacts: dict[str, dict]
    road_health: dict[str, Any]
    issues: list[str]
