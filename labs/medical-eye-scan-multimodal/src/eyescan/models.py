"""Packets for the scan graph."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field, field_validator

from labcore.workflow import RunState


class ScanMetadata(BaseModel):
    age: int = Field(ge=0, le=120)
    diabetes: bool
    iop_mmHg: float = Field(ge=0, le=80)
    laterality: str
    modality: str
    camera: str
    shape: list[int]


class Scan(BaseModel):
    case_id: str
    image: list[list[float]]
    metadata: ScanMetadata

    @field_validator("image")
    @classmethod
    def _rectangular(cls, v: list[list[float]]) -> list[list[float]]:
        if not v or any(len(r) != len(v[0]) for r in v):
            raise ValueError("image must be a rectangular 2-D array")
        return v


class Hypothesis(BaseModel):
    label: str
    confidence: float = Field(ge=0, le=1)
    supporting_cases: list[str]
    findings: list[str]


class ExplanationReport(BaseModel):
    banner: str
    summary: str
    findings: list[str]
    cited_case_ids: list[str]
    cited_reference_ids: list[str]
    feature_contributions: list[str] = []
    limitations: str


@dataclass
class ScanState(RunState):
    scan: dict[str, Any] = field(default_factory=dict)
    features: dict[str, float] = field(default_factory=dict)
    embedding: list[float] = field(default_factory=list)
    ood: dict[str, Any] = field(default_factory=dict)
    similar: list[dict] = field(default_factory=list)
    contributions: dict[str, Any] = field(default_factory=dict)
    references: list[dict] = field(default_factory=list)
    hypotheses: list[dict] = field(default_factory=list)
    abstain: bool = False
    report: dict[str, Any] = field(default_factory=dict)


@dataclass
class OphthalmologistReview:
    run_id: str
    case_id: str
    banner: str
    hypotheses: list[dict]
    abstain: bool
    similar_case_ids: list[str]
    report: dict[str, Any]
    issues: list[str]
