"""Azure AI Vision / Foundry vision stand-in: deterministic, hand-written feature extraction on the
16x16 synthetic arrays, plus a text embedding of the report / metadata (feature hashing)."""

from __future__ import annotations

import numpy as np

from labcore.config import AzureStub

DISC, MACULA, N = (8, 12), (8, 5), 16
FEATURES = (
    "cup_ratio",
    "specks",
    "dark_dots",
    "macula_specks",
    "disc_mean",
    "background_mean",
    "background_std",
)


def _mask(center: tuple[int, int], radius: float) -> np.ndarray:
    rr, cc = np.mgrid[0:N, 0:N]
    return np.hypot(rr - center[0], cc - center[1]) <= radius


class VisionStandIn:
    def features(self, image: list[list[float]]) -> dict[str, float]:
        img = np.asarray(image, dtype=float)
        if img.shape != (N, N):
            raise ValueError(f"expected {N}x{N}, got {img.shape}")
        disc, mac = _mask(DISC, 2.6), _mask(MACULA, 1.6)
        rest = ~disc & ~mac
        return {
            "cup_ratio": float((img[disc] > 0.93).mean()),
            "specks": float((img[rest] > 0.8).sum()),
            "dark_dots": float((img[rest] < 0.15).sum()),
            "macula_specks": float((img[mac] > 0.8).sum()),
            "disc_mean": float(img[disc].mean()),
            "background_mean": float(img[rest].mean()),
            "background_std": float(img[rest].std()),
        }


class AzureVisionStub(AzureStub):
    service = "azure-ai-vision"


def metadata_text(meta: dict) -> str:
    words = [
        f"age{meta['age'] // 10 * 10}s",
        "diabetic" if meta["diabetes"] else "nondiabetic",
        "highpressure" if meta["iop_mmHg"] > 21 else "normalpressure",
        meta["modality"],
    ]
    return " ".join(words)
