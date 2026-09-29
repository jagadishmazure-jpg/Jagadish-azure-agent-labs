"""The five specialist agents. Each is plain, testable code; the workflow wraps them as MAF executors.

* SeismicAnalysisAgent: tiny recurrent time-series model over the seismogram (fixed weights, numpy;
  a stand-in for a trained LSTM/Transformer picker) + local-magnitude estimate + GNSS / tide gauges.
* SatelliteMonitoringAgent: Azure AI Vision stand-in over SAR tiles: water extent from backscatter,
  ground displacement from the interferogram.
* WeatherCorrelationAgent: rainfall intensity and antecedent soil moisture -> flood evidence.
* HistoricalPatternAgent: RAG over fifty years of invented records (AI Search stand-in).
* PredictionCoordinator: Bayesian ensemble with reliability weights and missing-sensor fallback."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

import numpy as np

from labcore.config import AzureStub
from labcore.search import HybridIndexStandIn
from signal_fusion import DATA
from signal_fusion.models import HAZARDS, Finding


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def logit(p: float) -> float:
    p = clamp(p, 1e-6, 1 - 1e-6)
    return math.log(p / (1 - p))


def sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


# ------------------------------------------------------------------------------------------- seismic
@dataclass
class TinyRecurrentPicker:
    """h_t = tanh(a*h_{t-1} + b*|x_t| + c). Fixed weights chosen by hand; it detects the onset and
    the coda length. Honest label: a deterministic stand-in, not a trained network."""

    a: float = 0.82
    b: float = 2.2
    c: float = -0.25
    trigger: float = 0.5

    def run(self, samples: list[float]) -> dict:
        x = np.abs(np.asarray(samples, dtype=float))
        floor = float(np.median(x))
        x = np.clip((x - floor) / ((x.max() - floor) or 1.0), 0, 1)  # contrast above the noise floor
        h, hs = 0.0, []
        for v in x:
            h = math.tanh(self.a * h + self.b * v + self.c)
            hs.append(h)
        above = [i for i, v in enumerate(hs) if v > self.trigger]
        return {
            "detected": bool(above),
            "onset_index": above[0] if above else None,
            "active_samples": len(above),
            "peak_state": round(max(hs), 3),
        }


def local_magnitude(peak_um: float, distance_km: float) -> float:
    return (
        math.log10(max(peak_um, 1e-9))
        + 1.11 * math.log10(max(distance_km, 1.0))
        + 0.00189 * distance_km
        - 2.09
    )


@dataclass
class SeismicAnalysisAgent:
    picker: TinyRecurrentPicker = field(default_factory=TinyRecurrentPicker)
    name: str = "seismic-analysis-agent"

    def analyse(self, seismic: dict | None, displacement: dict | None, coastal: bool) -> Finding:
        ev = {h: {} for h in HAZARDS}
        feats: dict = {}
        weights: dict = {}
        notes: list[str] = []
        sources: list[str] = []
        if seismic:
            v = seismic["values"]
            pick = self.picker.run(v["samples"])
            peak = max(abs(s) for s in v["samples"]) * v["scale_um"]
            ml = round(local_magnitude(peak, v["distance_km"]), 2)
            feats.update(
                {
                    "magnitude": ml,
                    "depth_km": v["depth_km"],
                    "offshore": v["offshore"],
                    "distance_km": v["distance_km"],
                    **{f"pick_{k}": x for k, x in pick.items()},
                }
            )
            if not pick["detected"]:
                notes.append("no onset picked; magnitude from noise floor")
            shallow = clamp((v["depth_km"] - 70) / 100, 0, 1)
            near = clamp((v["distance_km"] - 50) / 100, 0, 1)
            ev["quake"]["seismic"] = 3.0 * clamp((ml - 5.0) / 1.0, -1, 2.5) - 1.5 * shallow - 1.0 * near
            if coastal and v["offshore"]:
                ev["tsunami"]["seismic"] = 3.0 * clamp((ml - 6.8) / 0.7, -1.5, 2.5) - 1.5 * clamp(
                    (v["depth_km"] - 60) / 100, 0, 1
                )
            elif coastal:
                ev["tsunami"]["seismic"] = -3.0
            ev["flood"]["seismic"] = 0.4 * clamp((ml - 6.0) / 1.5, 0, 1)  # dam / levee damage path
            weights["seismic"] = seismic["quality"]
            sources.append("seismic")
        if displacement:
            v = displacement["values"]
            feats.update({"gnss_uplift_mm": v["gnss_uplift_mm"], "tide_anomaly_m": v["tide_anomaly_m"]})
            ev["quake"]["displacement"] = 1.2 * clamp(abs(v["gnss_uplift_mm"]) / 30, 0, 1.5)
            if coastal:
                ev["tsunami"]["displacement"] = 3.0 * clamp((v["tide_anomaly_m"] - 0.1) / 0.4, -0.5, 2.5)
            weights["displacement"] = displacement["quality"]
            sources.append("displacement")
        return Finding(
            agent=self.name, sources=sources, features=feats, evidence=ev, weights=weights, notes=notes
        )


# ----------------------------------------------------------------------------------------- satellite
class VisionStandIn:
    """Azure AI Vision / Foundry vision stand-in for SAR tiles (deterministic image analysis)."""

    water_threshold = 0.2

    def analyze(
        self, backscatter: list[list[float]], interferogram: list[list[float]], wavelength_mm: float
    ) -> dict:
        b = np.asarray(backscatter, dtype=float)
        ph = np.asarray(interferogram, dtype=float)
        water = float((b < self.water_threshold).mean() * 100)
        disp = float(np.median(ph) * wavelength_mm / (4 * math.pi))
        return {
            "water_extent_pct": round(water, 1),
            "ground_disp_mm": round(disp, 1),
            "phase_noise": round(float(ph.std()), 4),
        }


class AzureVisionStub(AzureStub):
    service = "azure-ai-vision"


@dataclass
class SatelliteMonitoringAgent:
    vision: VisionStandIn = field(default_factory=VisionStandIn)
    name: str = "satellite-monitoring-agent"

    def analyse(self, sat: dict | None, coastal: bool, neighbour: tuple[str, dict] | None = None) -> Finding:
        ev = {h: {} for h in HAZARDS}
        fallbacks: dict[str, str] = {}
        use, weight = sat, (sat or {}).get("quality", 0.0)
        if use is None and neighbour is not None:
            nb_region, use = neighbour
            weight = use["quality"] * 0.5
            fallbacks["satellite"] = f"neighbour:{nb_region}"
        if use is None:
            return Finding(
                agent=self.name,
                sources=[],
                features={},
                evidence=ev,
                weights={},
                fallbacks={"satellite": "prior"},
                notes=["no SAR scene in window"],
            )
        v = use["values"]
        img = self.vision.analyze(v["backscatter"], v["interferogram_rad"], v["wavelength_mm"])
        ev["flood"]["satellite"] = 3.0 * clamp((img["water_extent_pct"] - 4) / 12, -1, 2)
        ev["quake"]["satellite"] = 1.0 * clamp(abs(img["ground_disp_mm"]) / 20, 0, 1.5)
        if coastal:
            ev["tsunami"]["satellite"] = 0.8 * clamp((img["water_extent_pct"] - 6) / 12, 0, 1.5)
        return Finding(
            agent=self.name,
            sources=["satellite"],
            features=img,
            evidence=ev,
            weights={"satellite": round(weight, 3)},
            fallbacks=fallbacks,
        )


# ------------------------------------------------------------------------------------------- weather
@dataclass
class WeatherCorrelationAgent:
    name: str = "weather-correlation-agent"

    def analyse(self, weather: dict | None) -> Finding:
        ev = {h: {} for h in HAZARDS}
        if weather is None:
            return Finding(
                agent=self.name,
                sources=[],
                features={},
                evidence=ev,
                weights={},
                fallbacks={"weather": "prior"},
                notes=["no weather observation in window"],
            )
        v = weather["values"]
        rain, rate, soil = v["rain_24h_mm"], v["rain_rate_mm_h"], v.get("soil_moisture_pct", 25.0)
        # wetter ground turns the same rain into more runoff: soil moisture scales the rain term
        runoff = 1.0 + 0.5 * clamp((soil - 30) / 20, -0.5, 1)
        llr = runoff * 2.5 * clamp((rain - 60) / 80, -1, 2.5) + 0.8 * clamp((rate - 10) / 20, -1, 1.5)
        ev["flood"]["weather"] = llr
        return Finding(
            agent=self.name,
            sources=["weather"],
            features={
                "rain_24h_mm": rain,
                "rain_rate_mm_h": rate,
                "soil_moisture_pct": soil,
                "runoff_factor": round(runoff, 3),
            },
            evidence=ev,
            weights={"weather": weather["quality"]},
        )


# ---------------------------------------------------------------------------------------- historical
def load_archive() -> list[dict]:
    return [json.loads(x) for x in (DATA / "history_archive.jsonl").read_text().splitlines() if x.strip()]


def record_vector(hazard: str, severity: float) -> list[float]:
    return [1.0 if hazard == h else 0.0 for h in HAZARDS] + [severity]


@dataclass
class HistoricalPatternAgent:
    """Retrieves analog events for the region and returns how often each hazard reached high/severe."""

    index: HybridIndexStandIn = field(default_factory=lambda: HybridIndexStandIn("disaster-history"))
    name: str = "historical-pattern-agent"
    top: int = 6

    def __post_init__(self) -> None:
        if not self.index.docs:
            for r in load_archive():
                self.index.upsert(
                    {
                        "id": r["record_id"],
                        "text": r["text"],
                        "region_id": r["region_id"],
                        "vector": record_vector(r["hazard"], r["severity"]),
                        **r,
                    }
                )

    def analogs(self, region_id: str, region_name: str, leading: str, severity: float) -> list[dict]:
        hits = self.index.search(
            f"{region_name} {leading}",
            record_vector(leading, severity),
            top=self.top,
            filter={"region_id": region_id},
        )
        return [
            {
                "record_id": h.id,
                "year": h.doc["year"],
                "hazard": h.doc["hazard"],
                "level": h.doc["level"],
                "score": round(h.score, 4),
            }
            for h in hits
        ]

    def base_rates(self, region_id: str) -> dict[str, float]:
        recs = [d for d in self.index.docs.values() if d["region_id"] == region_id]
        n = len(recs) or 1
        return {
            h: (sum(1 for d in recs if d["hazard"] == h and d["level"] in {"high", "severe"}) + 0.5)
            / (n + 1.5)
            for h in HAZARDS
        }


# -------------------------------------------------------------------------------------- coordinator
IMPORTANCE = {  # share of a hazard's information normally carried by each source (for uncertainty)
    "flood": {"weather": 0.4, "satellite": 0.35, "seismic": 0.05, "displacement": 0.0},
    "quake": {"seismic": 0.55, "displacement": 0.2, "satellite": 0.15, "weather": 0.0},
    "tsunami": {"seismic": 0.45, "displacement": 0.4, "satellite": 0.1, "weather": 0.0},
}
MIN_QUALITY = 0.3
HISTORY_WEIGHT = 0.5


@dataclass
class PredictionCoordinator:
    """Posterior log-odds = prior log-odds + sum over sources of weight * LLR (+ a small history term).
    A source that is missing or below MIN_QUALITY contributes nothing (the posterior falls back to the
    prior for that part of the evidence) and widens the hazard's uncertainty by its importance."""

    name: str = "prediction-coordinator-agent"

    def fuse(
        self, priors: dict[str, float], findings: list[Finding], base_rates: dict[str, float], coastal: bool
    ) -> dict:
        weights: dict[str, float] = {}
        evidence: dict[str, dict[str, float]] = {h: {} for h in HAZARDS}
        fallbacks: dict[str, str] = {}
        for f in findings:
            fallbacks.update(f.fallbacks)
            for s, w in f.weights.items():
                if w < MIN_QUALITY:
                    fallbacks[s] = "prior (low quality)"
                    continue
                weights[s] = w
            for h, per in f.evidence.items():
                for s, llr in per.items():
                    if s in weights:
                        evidence[h][s] = llr
        out: dict = {
            "posterior": {},
            "contributions": {},
            "uncertainty": {},
            "fallbacks": fallbacks,
            "weights": weights,
        }
        for h in HAZARDS:
            prior = priors[h]
            contrib = {s: round(weights[s] * llr, 4) for s, llr in evidence[h].items()}
            hist = HISTORY_WEIGHT * clamp(logit(base_rates[h]) - logit(max(prior, 1e-3)), -1, 1)
            if h == "tsunami" and not coastal:
                contrib, hist = {}, 0.0
            z = logit(prior) + sum(contrib.values()) + hist
            missing = sum(
                IMPORTANCE[h][s] * (0.5 if fallbacks.get(s, "").startswith("neighbour") else 1.0)
                for s in IMPORTANCE[h]
                if s not in weights or fallbacks.get(s, "").startswith("neighbour")
            )
            out["posterior"][h] = round(sigmoid(z), 4)
            out["contributions"][h] = {**contrib, "history": round(hist, 4)}
            out["uncertainty"][h] = round(min(1.0, 0.05 + missing), 3)
        return out
