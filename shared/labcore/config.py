"""One switch for every adapter: `LAB_MODE=offline` (default) or `LAB_MODE=azure`.

Labs never read environment variables directly; they ask `settings()` and `pick()`. In azure mode
`pick()` returns the stub adapter, which raises `AdapterNotConfigured` on first use. That keeps the
real-Azure seam visible in code and tests without any cloud calls."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")


class AdapterNotConfigured(RuntimeError):
    """Raised by every real-Azure adapter stub. The labs are never deployed; see the root README."""


@dataclass(frozen=True)
class LabSettings:
    mode: str = "offline"
    foundry_project_endpoint: str = ""
    data_zone: str = "us"
    managed_identity_client_id: str = ""
    appinsights_connection_string: str = ""
    trace_console: bool = False

    @property
    def azure(self) -> bool:
        return self.mode == "azure"

    @classmethod
    def from_env(cls) -> LabSettings:
        e = os.environ.get
        mode = e("LAB_MODE", "offline").strip().lower()
        if mode not in {"offline", "azure"}:
            raise ValueError(f"LAB_MODE must be offline or azure, got {mode!r}")
        return cls(
            mode=mode,
            foundry_project_endpoint=e("FOUNDRY_PROJECT_ENDPOINT", "").strip(),
            data_zone=e("FOUNDRY_DATA_ZONE", "us").strip().lower(),
            managed_identity_client_id=e("AZURE_CLIENT_ID", "").strip(),
            appinsights_connection_string=e("APPLICATIONINSIGHTS_CONNECTION_STRING", "").strip(),
            trace_console=e("LAB_TRACE_CONSOLE", "0") == "1",
        )


def settings() -> LabSettings:
    return LabSettings.from_env()


def pick(offline: Callable[[], T], azure: Callable[[], T], s: LabSettings | None = None) -> T:
    """Return the offline stand-in or the Azure adapter according to the mode."""
    s = s or settings()
    return azure() if s.azure else offline()


class AzureStub:
    """Base for real-Azure adapter stubs: construction is cheap, any use raises."""

    service = "azure"

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.args = args
        self.kwargs = kwargs

    def _unwired(self, op: str):
        raise AdapterNotConfigured(
            f"{self.service}.{op}: real Azure adapter is a stub in this portfolio (LAB_MODE=azure). "
            "Wire the SDK call here after provisioning; nothing is deployed from this repo."
        )

    def __getattr__(self, op: str):
        if op.startswith("_"):
            raise AttributeError(op)
        return lambda *a, **k: self._unwired(op)
