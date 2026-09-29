"""Pydantic packets passed between MCP tools, agents and the reviewer. Every hop validates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

from labcore.workflow import RunState


class Line(BaseModel):
    text: str
    confidence: float = Field(ge=0, le=1)


class Table(BaseModel):
    table_id: str
    confidence: float = Field(ge=0, le=1)
    rows: list[list[str]]


class Page(BaseModel):
    page: int
    lines: list[Line]
    tables: list[Table] = []


class LayoutResult(BaseModel):
    doc_id: str
    domain: Literal["banking", "insurance", "healthcare"]
    title: str
    pages: list[Page]


class PageReliability(BaseModel):
    page: int
    mean_confidence: float
    non_word_ratio: float
    symbol_ratio: float
    junk_score: float
    accepted: bool
    reason: str = ""


class ClausePacket(BaseModel):
    clause_id: str
    section: int
    heading: str
    text: str
    pages: list[int]
    ocr_confidence: float


class ClauseList(BaseModel):
    clauses: list[ClausePacket]


class TablePacket(BaseModel):
    table_id: str
    page: int
    header: list[str]
    rows: list[list[str]]
    confidence: float


class TableReview(BaseModel):
    table_id: str
    page: int
    reason: str


class TableResult(BaseModel):
    tables: list[TablePacket]
    needs_review: list[TableReview]


class ClauseClassification(BaseModel):
    clause_id: str
    label: str
    rationale: str


@dataclass
class DocState(RunState):
    doc_id: str = ""
    layout: dict[str, Any] = field(default_factory=dict)
    reliability: list[dict] = field(default_factory=list)
    clauses: list[dict] = field(default_factory=list)
    tables: list[dict] = field(default_factory=list)
    tables_for_review: list[dict] = field(default_factory=list)
    classified: list[dict] = field(default_factory=list)
    route: dict[str, Any] = field(default_factory=dict)
    audit: dict[str, Any] = field(default_factory=dict)
    redo_count: int = 0
    uncertainty: float = 0.0


@dataclass
class ComplianceReview:
    run_id: str
    doc_id: str
    domain: str
    clauses: list[dict]
    tables: list[dict]
    tables_for_review: list[dict]
    rejected_pages: list[int]
    review_items: list[str]
    route: dict[str, Any]
    audit: dict[str, Any]
    uncertainty: float
    issues: list[str]
