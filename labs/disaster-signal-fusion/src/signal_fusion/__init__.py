"""Disaster signal fusion lab: seismic, satellite, weather and ground-displacement signals fused
into flood / earthquake / tsunami risk for an operations desk. A human decides on any alert."""

from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parents[2]
DATA = LAB_ROOT / "data"
