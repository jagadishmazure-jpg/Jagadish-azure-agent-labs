"""Builds the synthetic "retinal scan" fixtures: 16x16 float arrays drawn from hand-made templates.

These are not images of eyes and contain no patient data. Each class adds a crude pattern to a
shared background so the lab has something a feature extractor can tell apart:

* normal: background + optic disc with a small cup
* diabetic_retinopathy: + scattered bright specks and dark dots away from the disc
* glaucoma: optic disc with a large cup (high cup-to-disc ratio)
* amd: cluster of bright specks around the macula

    python data/gen_fixtures.py"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
GOLD = HERE.parent / "evals" / "gold"
LABELS = ["normal", "diabetic_retinopathy", "glaucoma", "amd"]
N = 16
DISC = (8, 12)  # row, col
MACULA = (8, 5)

REPORT_PHRASES = {
    "normal": [
        "Disc margins crisp, small central cup.",
        "No specks or dots in the posterior pole.",
        "Macula looks even.",
    ],
    "diabetic_retinopathy": [
        "Scattered bright specks consistent with hard exudates.",
        "Several dark dots suggesting microaneurysms or blot haemorrhages.",
        "Disc itself unremarkable.",
    ],
    "glaucoma": [
        "Cup occupies most of the disc; cup-to-disc ratio looks raised.",
        "Rim thin inferiorly.",
        "Posterior pole otherwise quiet.",
    ],
    "amd": [
        "Cluster of yellow-white specks at the macula, drusen-like.",
        "Disc normal.",
        "No haemorrhage seen.",
    ],
}
REFERENCES = [
    {
        "ref_id": "REF-DR-01",
        "label": "diabetic_retinopathy",
        "text": "Reference atlas note: bright waxy specks plus dark dots scattered away from the disc point to diabetic retinal damage; grade by count and spread.",
    },
    {
        "ref_id": "REF-GL-01",
        "label": "glaucoma",
        "text": "Reference atlas note: an enlarged pale cup inside the optic disc, especially with raised eye pressure, is the classic sign of glaucomatous nerve loss.",
    },
    {
        "ref_id": "REF-AMD-01",
        "label": "amd",
        "text": "Reference atlas note: small pale deposits grouped at the macula in older adults suggest age-related macular degeneration.",
    },
    {
        "ref_id": "REF-N-01",
        "label": "normal",
        "text": "Reference atlas note: a healthy scan shows an evenly lit background, a pink disc with a small cup and no specks or dots.",
    },
]


def disc(img: np.ndarray, cup_r: float, rng) -> None:
    for r in range(N):
        for c in range(N):
            d = np.hypot(r - DISC[0], c - DISC[1])
            if d <= 2.6:
                img[r, c] = 0.75 + rng.normal(0, 0.02)
            if d <= cup_r:
                img[r, c] = 0.97


def make(label: str, seed: int) -> np.ndarray:
    """Classes overlap on purpose (mild disease, borderline cups, stray specks) so calibration matters."""
    rng = np.random.default_rng(seed)
    rr, cc = np.mgrid[0:N, 0:N]
    img = 0.35 - 0.08 * np.hypot(rr - 7.5, cc - 7.5) / 10 + rng.normal(0, 0.04, (N, N))
    cup = float(rng.uniform(1.3, 2.5)) if label == "glaucoma" else float(rng.uniform(0.4, 1.5))
    disc(img, cup, rng)
    if label == "diabetic_retinopathy":
        for _ in range(int(rng.integers(1, 7))):
            img[int(rng.integers(2, 14)), int(rng.integers(1, 9))] = 0.9
        for _ in range(int(rng.integers(0, 5))):
            img[int(rng.integers(2, 14)), int(rng.integers(1, 9))] = 0.05
    if label == "amd":
        for _ in range(int(rng.integers(1, 6))):
            r = int(np.clip(MACULA[0] + rng.integers(-1, 2), 0, N - 1))
            c = int(np.clip(MACULA[1] + rng.integers(-1, 2), 0, N - 1))
            img[r, c] = 0.85
    if rng.uniform() < 0.3:  # stray artefact on any class
        img[int(rng.integers(0, N)), int(rng.integers(0, 8))] = 0.88
    return np.clip(img, 0, 1)


def metadata(label: str, rng) -> dict:
    age = int(rng.integers(62, 85)) if label == "amd" else int(rng.integers(35, 80))
    diabetic = bool(rng.uniform() < (0.9 if label == "diabetic_retinopathy" else 0.2))
    iop = round(float(rng.normal(26, 3) if label == "glaucoma" else rng.normal(15, 2.5)), 1)
    return {
        "age": age,
        "diabetes": diabetic,
        "iop_mmHg": iop,
        "laterality": ["OD", "OS"][int(rng.integers(0, 2))],
        "modality": "fundus",
        "camera": "synthetic-cam-1",
        "shape": [N, N],
    }


def case(split: str, i: int, label: str, seed: int) -> dict:
    rng = np.random.default_rng(seed + 7)
    phrases = REPORT_PHRASES[label]
    return {
        "case_id": f"{split[:3].upper()}-{i:03d}",
        "split": split,
        "label": label,
        "metadata": metadata(label, rng),
        "report": " ".join(phrases[j] for j in rng.permutation(len(phrases))[:2])
        if split == "library"
        else "",
        "image": [[round(float(v), 3) for v in row] for row in make(label, seed)],
    }


def ood_cases() -> list[dict]:
    rng = np.random.default_rng(99)
    noise = rng.uniform(0, 1, (N, N))
    blank = np.zeros((N, N))
    oct_meta = {
        "age": 60,
        "diabetes": False,
        "iop_mmHg": 15.0,
        "laterality": "OD",
        "modality": "oct",
        "camera": "synthetic-oct",
        "shape": [N, N],
    }
    base_meta = {**oct_meta, "modality": "fundus", "camera": "synthetic-cam-1"}
    inverted = 1 - make("normal", 4242)
    return [
        {
            "case_id": "OOD-001",
            "split": "ood",
            "label": "ood",
            "metadata": base_meta,
            "report": "",
            "image": [[round(float(v), 3) for v in r] for r in noise],
        },
        {
            "case_id": "OOD-002",
            "split": "ood",
            "label": "ood",
            "metadata": base_meta,
            "report": "",
            "image": blank.tolist(),
        },
        {
            "case_id": "OOD-003",
            "split": "ood",
            "label": "ood",
            "metadata": oct_meta,
            "report": "",
            "image": [[round(float(v), 3) for v in r] for r in make("normal", 777)],
        },
        {
            "case_id": "OOD-004",
            "split": "ood",
            "label": "ood",
            "metadata": base_meta,
            "report": "",
            "image": [[round(float(v), 3) for v in r] for r in inverted],
        },
    ]


def build() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {"library": [], "calibration": [], "test": []}
    sizes = {"library": 10, "calibration": 8, "test": 8}
    seed = 1000
    for split, k in sizes.items():
        i = 0
        for label in LABELS:
            for _ in range(k):
                seed += 1
                i += 1
                out[split].append(case(split, i, label, seed))
    out["ood"] = ood_cases()
    return out


if __name__ == "__main__":
    GOLD.mkdir(parents=True, exist_ok=True)
    data = build()
    (HERE / "library.json").write_text(json.dumps(data["library"]) + "\n")
    (HERE / "calibration.json").write_text(json.dumps(data["calibration"]) + "\n")
    (HERE / "references.json").write_text(json.dumps(REFERENCES, indent=1) + "\n")
    (GOLD / "test_cases.json").write_text(json.dumps(data["test"]) + "\n")
    (GOLD / "ood_cases.json").write_text(json.dumps(data["ood"]) + "\n")
    print({k: len(v) for k, v in data.items()})
