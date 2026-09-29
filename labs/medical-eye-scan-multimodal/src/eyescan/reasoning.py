"""Constrained reasoning: hypotheses may only come from the fixed label set, every hypothesis must
be supported by retrieved labeled cases, and confidence is temperature-calibrated on a held-out
calibration split. Below the abstain threshold the system says so instead of guessing."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from eyescan import LABELS
from eyescan.knowledge import CaseLibrary, load
from eyescan.vision import VisionStandIn

VOTE_SCALE = 4.0
ABSTAIN_BELOW = 0.5


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def metadata_prior(meta: dict) -> dict[str, float]:
    """Small log-score nudges from patient metadata (never enough to outvote the images alone)."""
    return {
        "normal": 0.0,
        "diabetic_retinopathy": 0.6 if meta["diabetes"] else -0.3,
        "glaucoma": 0.8 * clamp((meta["iop_mmHg"] - 21) / 5, -1, 1),
        "amd": 0.5 * clamp((meta["age"] - 60) / 15, -1, 1),
    }


def raw_scores(similar: list[dict], meta: dict) -> dict[str, float]:
    s = metadata_prior(meta)
    for h in similar:
        s[h["label"]] += VOTE_SCALE / (1.0 + h["distance"])
    return s


def softmax(scores: dict[str, float], t: float) -> dict[str, float]:
    m = max(scores.values())
    e = {k: math.exp((v - m) / t) for k, v in scores.items()}
    z = sum(e.values())
    return {k: v / z for k, v in e.items()}


def fit_temperature(rows: list[tuple[dict[str, float], str]]) -> float:
    """Grid search for the temperature that minimises negative log-likelihood on calibration rows."""
    best_t, best = 1.0, float("inf")
    for t in np.round(np.arange(0.2, 6.01, 0.1), 2):
        nll = -sum(math.log(max(softmax(s, float(t))[y], 1e-9)) for s, y in rows)
        if nll < best:
            best_t, best = float(t), nll
    return best_t


FINDING_TEXT = {
    "cup_ratio": ("cup_ratio", 0.3, "large cup relative to the disc"),
    "specks": ("specks", 2, "bright specks outside the disc"),
    "dark_dots": ("dark_dots", 2, "dark dots outside the disc"),
    "macula_specks": ("macula_specks", 2, "specks clustered at the macula"),
}


def findings(feats: dict[str, float]) -> list[str]:
    out = [f"{txt} ({feats[k]:.2f})" for k, (_, thr, txt) in FINDING_TEXT.items() if feats[k] >= thr]
    return out or ["no focal pattern above threshold"]


@dataclass
class Reasoner:
    library: CaseLibrary
    temperature: float = 1.0
    calibrated: bool = False
    vision: VisionStandIn = field(default_factory=VisionStandIn)

    def calibrate(self, cases: list[dict] | None = None) -> float:
        rows = []
        for c in cases or load("calibration.json"):
            emb = self.library.embed(self.vision.features(c["image"]))
            rows.append((raw_scores(self.library.similar(emb, c["metadata"]), c["metadata"]), c["label"]))
        self.temperature, self.calibrated = fit_temperature(rows), True
        return self.temperature

    def hypotheses(self, similar: list[dict], meta: dict, feats: dict[str, float]) -> tuple[list[dict], bool]:
        probs = softmax(raw_scores(similar, meta), self.temperature)
        out = []
        for label in sorted(LABELS, key=lambda k: -probs[k]):
            support = [h["case_id"] for h in similar if h["label"] == label]
            if not support:
                continue  # constrained: no labeled precedent retrieved -> not offered as a hypothesis
            out.append(
                {
                    "label": label,
                    "confidence": round(probs[label], 4),
                    "supporting_cases": support,
                    "findings": findings(feats),
                }
            )
        abstain = not out or out[0]["confidence"] < ABSTAIN_BELOW
        return out, abstain


def explain(reasoner: Reasoner, feats: dict[str, float], meta: dict, label: str) -> dict:
    """Contribution of each image feature to the calibrated log-odds of `label`
    (baseline = library mean feature values). Log-odds, not probability, so a saturated
    0.99 still shows which features carried it."""
    from eyescan.knowledge import FEATURES
    from labcore.explain import contributions

    lib = reasoner.library

    def f(v):
        emb = ((np.asarray(v) - lib.mu) / lib.sd).tolist()
        p = softmax(raw_scores(lib.similar(emb, meta), meta), reasoner.temperature)[label]
        p = min(max(p, 1e-4), 1 - 1e-4)
        return math.log(p / (1 - p))

    return contributions(f, [feats[k] for k in FEATURES], lib.mu.tolist(), FEATURES)
