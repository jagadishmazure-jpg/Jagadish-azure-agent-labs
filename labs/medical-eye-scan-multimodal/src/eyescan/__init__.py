"""Retinal-scan research triage lab. NOT A MEDICAL DEVICE: synthetic arrays only, research demo.
No output of this package is a diagnosis, and nothing is ever written to a health record."""

from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parents[2]
DATA = LAB_ROOT / "data"
BANNER = "NOT A MEDICAL DEVICE - research demo on synthetic data; not for clinical use"
LABELS = ("normal", "diabetic_retinopathy", "glaucoma", "amd")
