"""Human-in-the-loop types. Every lab ends its graph with `ctx.request_info(<ReviewPacket>, Decision)`;
nothing with a side effect runs until a named person answers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Decision:
    approved: bool
    reviewer: str
    note: str = ""
    overrides: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.reviewer.strip():
            raise ValueError("a decision needs a named reviewer")
