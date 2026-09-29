"""Anomaly detectors and the read-only detector registry.

* `IsolationForestDetector` (scikit-learn) is the default; `ZScoreDetector` is a deterministic fallback
  used automatically if scikit-learn cannot be imported.
* `DetectorRegistry.load_champion()` rebuilds the registered champion from its recorded parameters and
  verifies the training-data hash. The workflow only ever calls `load_champion()`: it cannot fit,
  retrain or promote. Promotion lives in `turbine_cl.promotion` and is run by a person."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from turbine_cl import DATA, REGISTRY
from turbine_cl.features import FEATURES, matrix

try:  # pragma: no cover - exercised implicitly
    from sklearn.ensemble import IsolationForest

    HAVE_SKLEARN = True
except ImportError:  # pragma: no cover
    HAVE_SKLEARN = False


class RegistryError(RuntimeError):
    pass


@dataclass
class ZScoreDetector:
    z_limit: float = 4.0
    kind: str = "zscore"
    mu: np.ndarray | None = None
    sd: np.ndarray | None = None

    def fit(self, x: np.ndarray) -> ZScoreDetector:
        self.mu, self.sd = x.mean(0), x.std(0) + 1e-6
        return self

    def z(self, x: np.ndarray) -> np.ndarray:
        return (x - self.mu) / self.sd

    def flags(self, x: np.ndarray) -> np.ndarray:
        return np.abs(self.z(x)[:, :-1]).max(1) > self.z_limit  # ambient temperature alone is not a fault


@dataclass
class IsolationForestDetector(ZScoreDetector):
    n_estimators: int = 100
    contamination: float = 0.02
    random_state: int = 7
    kind: str = "isolation_forest"
    model: object | None = None

    def fit(self, x: np.ndarray) -> IsolationForestDetector:
        super().fit(x)
        self.model = IsolationForest(
            n_estimators=self.n_estimators, contamination=self.contamination, random_state=self.random_state
        ).fit(self.z(x))
        return self

    def flags(self, x: np.ndarray) -> np.ndarray:
        return self.model.predict(self.z(x)) == -1


def make_detector(params: dict):
    if params.get("kind") == "isolation_forest" and HAVE_SKLEARN:
        return IsolationForestDetector(
            n_estimators=params["n_estimators"],
            contamination=params["contamination"],
            random_state=params["random_state"],
        )
    return ZScoreDetector(z_limit=params.get("z_limit", 4.0))


def data_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def train_rows(name: str) -> list[dict]:
    return json.loads((DATA / name).read_text())


@dataclass
class WindowResult:
    anomalous: bool
    flagged_rows: int
    signature: list[float]
    top_features: list[str]


@dataclass
class DetectorRegistry:
    path: Path = REGISTRY
    _cache: dict = field(default_factory=dict)

    def read(self) -> dict:
        return json.loads(self.path.read_text())

    def champion_entry(self) -> dict:
        reg = self.read()
        return next(v for v in reg["versions"] if v["version"] == reg["champion"])

    def load_champion(self):
        entry = self.champion_entry()
        key = (entry["version"], entry["training_data_hash"])
        if key in self._cache:
            return self._cache[key], entry
        src = DATA / entry["training_data"]
        if data_hash(src) != entry["training_data_hash"]:
            raise RegistryError(
                f"{entry['version']}: training data changed since registration; refusing to rebuild"
            )
        det = make_detector(entry["params"]).fit(matrix(train_rows(entry["training_data"])))
        self._cache[key] = det
        return det, entry


def score_window(det, rows: list[dict], min_flagged: int = 3) -> WindowResult:
    x = matrix(rows)
    f = det.flags(x)
    z = det.z(x)
    sel = z[f] if f.any() else z
    sig = sel.mean(0)
    order = np.argsort(-np.abs(sig[:-1]))[:3]
    return WindowResult(
        bool(f.sum() >= min_flagged),
        int(f.sum()),
        [round(float(v), 3) for v in sig],
        [FEATURES[i] for i in order],
    )
