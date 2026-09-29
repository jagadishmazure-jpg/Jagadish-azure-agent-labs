"""Wind turbine continual-learning lab: telemetry -> anomaly -> similar episodes -> diagnosis ->
recommendation -> technician -> episode memory. Detector changes go only through an eval-gated
promotion pipeline, never through an agent."""

from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parents[2]
DATA = LAB_ROOT / "data"
REGISTRY = LAB_ROOT / "models" / "registry.json"
