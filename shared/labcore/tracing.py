"""OpenTelemetry tracing. App Insights would be used when a connection string is present (stubbed:
the azure-monitor exporter is not a dependency), the console exporter when LAB_TRACE_CONSOLE=1,
otherwise an SDK provider with an in-memory exporter that tests can inspect."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from labcore.config import LabSettings, settings

_memory = InMemorySpanExporter()
_backend: str | None = None


def configure_tracing(service_name: str = "azure-agent-labs", s: LabSettings | None = None) -> str:
    """Idempotent; returns the backend in use."""
    global _backend
    if _backend:
        return _backend
    s = s or settings()
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(SimpleSpanProcessor(_memory))
    if s.appinsights_connection_string:
        # Real wiring would be azure.monitor.opentelemetry.configure_azure_monitor(); kept out on purpose.
        _backend = "appinsights-stub+memory"
    elif s.trace_console:
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
        _backend = "console"
    else:
        _backend = "memory"
    trace.set_tracer_provider(provider)
    return _backend


def finished_spans() -> list:
    return list(_memory.get_finished_spans())


def clear_spans() -> None:
    _memory.clear()


@contextmanager
def span(name: str, **attrs: Any):
    configure_tracing()
    with trace.get_tracer("labcore").start_as_current_span(name) as s:
        for k, v in attrs.items():
            if v is not None:
                s.set_attribute(f"lab.{k}", v if isinstance(v, str | int | float | bool) else str(v))
        yield s
