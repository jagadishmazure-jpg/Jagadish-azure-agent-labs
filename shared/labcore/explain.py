"""Per-feature contribution scores for a single prediction.

Uses SHAP (KernelExplainer against one baseline row) when the `shap` package is installed and
`method="auto"`; otherwise a deterministic ablation importance: contribution_i = f(x) - f(x with
feature i reset to its baseline). Both explain the same quantity: how much each feature moved the
score away from the baseline (a "typical" input)."""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np


def _has_shap() -> bool:
    try:
        import shap  # noqa: F401
    except ImportError:
        return False
    return True


def contributions(
    fn: Callable[[np.ndarray], float],
    x: Sequence[float],
    baseline: Sequence[float],
    names: Sequence[str],
    method: str = "auto",
    top: int | None = None,
) -> dict:
    x, b = np.asarray(x, float), np.asarray(baseline, float)
    use_shap = method == "shap" or (method == "auto" and _has_shap())
    if use_shap:  # pragma: no cover - optional dependency
        import shap

        ex = shap.KernelExplainer(lambda m: np.array([fn(r) for r in m]), b[None, :])
        vals = np.asarray(ex.shap_values(x[None, :], silent=True)).reshape(-1)
        used = "shap_kernel"
    else:
        fx = fn(x)
        vals = np.empty(len(x))
        for i in range(len(x)):
            xi = x.copy()
            xi[i] = b[i]
            vals[i] = fx - fn(xi)
        used = "ablation"
    rows = sorted(
        (
            {"feature": n, "value": round(float(v), 4), "contribution": round(float(c), 4)}
            for n, v, c in zip(names, x, vals, strict=True)
        ),
        key=lambda r: -abs(r["contribution"]),
    )
    return {
        "method": used,
        "score": round(float(fn(x)), 4),
        "baseline_score": round(float(fn(b)), 4),
        "features": rows[:top] if top else rows,
    }


def render(c: dict, k: int = 3) -> list[str]:
    return [
        f"{r['feature']} {'+' if r['contribution'] >= 0 else ''}{r['contribution']:.3f}"
        for r in c["features"][:k]
    ]
