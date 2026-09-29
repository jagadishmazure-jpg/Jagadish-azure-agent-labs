"""Eval gate for the disaster-signal-fusion lab (offline, deterministic).

    python labs/disaster-signal-fusion/evals/run_eval.py [--out evals-out]

Metrics
* signal_usage_rate: share of (gold case, required source) pairs whose contribution to the hazard is
  non-zero; catches a fusion that quietly ignores a signal such as rainfall.
* rain_sensitivity: share of scenarios where adding 100 mm of rain raises the weather evidence and
  never lowers the flood posterior.
* replay_hazard_accuracy / replay_level_within_one / replay_level_exact: held-out historical replay.
* fallback_flagged: replay events with a dead sensor must record a fallback.
* no_public_alert: every approved run ends with public_alert_sent == False."""

from __future__ import annotations

import argparse
import asyncio
import copy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "src"), str(HERE.parents[2] / "shared")]

from labcore.evals import Threshold, gate, load_jsonl, write_report  # noqa: E402
from labcore.hitl import Decision  # noqa: E402
from signal_fusion.service import OpsDesk, scenarios  # noqa: E402

LEVELS = ["low", "elevated", "high", "severe"]
THRESHOLDS = [
    Threshold("signal_usage_rate", ">=", 1.0),
    Threshold("rain_sensitivity", ">=", 1.0),
    Threshold("replay_hazard_accuracy", ">=", 0.85),
    Threshold("replay_level_within_one", ">=", 1.0),
    Threshold("fallback_flagged", ">=", 1.0),
    Threshold("no_public_alert", ">=", 1.0),
]


async def _assess(readings: list[dict], region: str, approve: bool = False):
    desk = OpsDesk()
    desk.publish(readings)
    res = await desk.assess(region)
    out = None
    if approve:
        out = (await desk.decide(res.run_id, res.request_id, Decision(True, "eval-officer"))).output
    return res.pending, out


def _with_more_rain(readings: list[dict]) -> list[dict]:
    rs = copy.deepcopy(readings)
    for r in rs:
        if r["source"] == "weather":
            r["payload"]["rain_24h_mm"] += 100
            r["payload"]["rain_rate_mm_h"] += 10
    return rs


async def evaluate():
    rows, used_hits, used_total = [], 0, 0
    sc = scenarios()
    for case in load_jsonl(HERE / "gold" / "signal_usage.jsonl"):
        review, _ = await _assess(sc[case["scenario"]], case["region_id"])
        contrib = review.contributions[case["hazard"]]
        for s in case["must_use"]:
            used_total += 1
            ok = abs(contrib.get(s, 0.0)) > 0.05
            used_hits += ok
            rows.append(
                {
                    "kind": "signal_usage",
                    "case": case["case_id"],
                    "source": s,
                    "ok": ok,
                    "contribution": contrib.get(s),
                }
            )
    sens_ok, sens_n = 0, 0
    for name, rs in sc.items():
        if not any(r["source"] == "weather" for r in rs):
            continue
        region = rs[0]["region_id"]
        base, _ = await _assess(rs, region)
        wet, _ = await _assess(_with_more_rain(rs), region)
        ok = (
            wet.contributions["flood"].get("weather", 0) > base.contributions["flood"].get("weather", 0)
            and wet.risk["scores"]["flood"] >= base.risk["scores"]["flood"]
        )
        sens_n += 1
        sens_ok += ok
        rows.append({"kind": "rain_sensitivity", "scenario": name, "ok": ok})
    replay = load_jsonl(HERE / "gold" / "replay.jsonl")
    hz_ok = lv1 = lv_exact = fb_ok = fb_n = alert_ok = 0
    for ev in replay:
        review, out = await _assess(ev["readings"], ev["region_id"], approve=True)
        h = review.primary_hazard == ev["observed_hazard"]
        d = abs(LEVELS.index(review.level) - LEVELS.index(ev["observed_level"]))
        hz_ok += h
        lv1 += d <= 1
        lv_exact += d == 0
        present = {r["source"] for r in ev["readings"]}
        if present != {"seismic", "weather", "satellite", "displacement"}:
            fb_n += 1
            fb_ok += bool(review.fallbacks)
        alert_ok += out["public_alert_sent"] is False
        rows.append(
            {
                "kind": "replay",
                "event": ev["event_id"],
                "predicted": [review.primary_hazard, review.level],
                "observed": [ev["observed_hazard"], ev["observed_level"]],
                "scores": review.risk["scores"],
            }
        )
    n = len(replay)
    metrics = {
        "signal_usage_rate": used_hits / used_total,
        "rain_sensitivity": sens_ok / sens_n,
        "replay_hazard_accuracy": hz_ok / n,
        "replay_level_within_one": lv1 / n,
        "replay_level_exact": lv_exact / n,
        "fallback_flagged": fb_ok / fb_n if fb_n else 1.0,
        "no_public_alert": alert_ok / n,
    }
    return gate("disaster-signal-fusion", metrics, THRESHOLDS, rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="evals-out")
    a = ap.parse_args(argv)
    report = asyncio.run(evaluate())
    path = write_report(report, a.out)
    import json

    print(json.dumps(report.to_dict(), indent=2))
    for r in report.rows:
        if r["kind"] == "replay":
            print(r)
    print(f"report: {path}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
