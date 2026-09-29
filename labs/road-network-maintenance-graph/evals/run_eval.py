"""Eval gate for the road maintenance lab.

    python labs/road-network-maintenance-graph/evals/run_eval.py [--out evals-out]

* detour_within_15pct: predicted extra vehicle-minutes vs the (synthetic) historical closure record,
  within 15% or 10 vehicle-minutes
* disconnection_accuracy / hospital_access_accuracy / stranded_trips_accuracy: exact match per closure
* pairwise_order_accuracy: planner-approved "A should outrank B" pairs (connectivity over potholes)
* budget_respected: plan total <= budget for several budgets, and the guard raises on overspend
* route_quality: shortest paths from the graph agents match the optimal travel time and are valid walks
* must_fix_included / plan_above_median: recommendation usefulness - the plan at $400k contains the
  segments a planner marked must-fix, and its items score above the network median"""

from __future__ import annotations

import argparse
import asyncio
import itertools
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "src"), str(HERE.parents[2] / "shared")]

from labcore.evals import Threshold, gate, load_jsonl, write_report  # noqa: E402
from labcore.hitl import Decision  # noqa: E402
from roadgraph import graph_ops as ops  # noqa: E402
from roadgraph.service import PlanningDesk  # noqa: E402

THRESHOLDS = [
    Threshold("route_quality", ">=", 1.0),
    Threshold("detour_within_15pct", ">=", 1.0),
    Threshold("disconnection_accuracy", ">=", 1.0),
    Threshold("hospital_access_accuracy", ">=", 1.0),
    Threshold("stranded_trips_accuracy", ">=", 1.0),
    Threshold("pairwise_order_accuracy", ">=", 1.0),
    Threshold("must_fix_included", ">=", 1.0),
    Threshold("plan_above_median", ">=", 1.0),
    Threshold("budget_respected", ">=", 1.0),
    Threshold("no_work_orders", ">=", 1.0),
]


async def evaluate():
    rows = []
    g = ops.build_graph()
    dem = ops.demand()
    base = ops.trip_minutes(g, dem)
    closures = load_jsonl(HERE / "gold" / "closures.jsonl")
    det = disc = hosp = strand = 0
    for c in closures:
        imp = ops.closure_impact(g, c["segment_id"], dem, base)
        obs = c["observed_extra_vehicle_minutes"]
        ok = abs(imp["extra_vehicle_minutes"] - obs) <= max(0.15 * abs(obs), 10)
        det += ok
        disc += imp["disconnected"] == c["observed_disconnected"]
        hosp += imp["hospital_access_lost"] == c["observed_hospital_access_lost"]
        strand += imp["stranded_trips"] == c["observed_stranded_trips"]
        rows.append(
            {
                "kind": "closure",
                "id": c["closure_id"],
                "predicted": imp["extra_vehicle_minutes"],
                "observed": obs,
                "ok": ok,
            }
        )
    desk = PlanningDesk()
    res = await desk.plan(400_000)
    plan_ids = [i["segment_id"] for i in res.pending.plan["items"]]
    ranked = ops.priority(g, ops.features(g, dem))
    full_rank = {r["segment_id"]: i for i, r in enumerate(ranked)}
    median = sorted(r["score"] for r in ranked)[len(ranked) // 2]
    score = {r["segment_id"]: r["score"] for r in ranked}
    must = json.loads((HERE / "gold" / "must_fix.json").read_text())
    must_ok = sum(s in plan_ids for s in must["segments"]) / len(must["segments"])
    above = sum(score[s] > median for s in plan_ids) / (len(plan_ids) or 1)
    route_ok = 0
    routes = load_jsonl(HERE / "gold" / "routes.jsonl")
    for r in routes:
        path = ops.nx.shortest_path(g, r["origin"], r["dest"], weight="minutes")
        valid = all(g.has_edge(a, b) for a, b in itertools.pairwise(path))
        t = sum(g.edges[a, b]["minutes"] for a, b in itertools.pairwise(path))
        route_ok += valid and abs(t - r["minutes"]) < 1e-3
        rows.append({"kind": "route", **r, "predicted_minutes": round(t, 3)})
    pairs = load_jsonl(HERE / "gold" / "pairwise.jsonl")
    pair_ok = sum(full_rank[p["higher"]] < full_rank[p["lower"]] for p in pairs)
    for p in pairs:
        rows.append({"kind": "pairwise", **p, "ok": full_rank[p["higher"]] < full_rank[p["lower"]]})
    budgets_ok, budgets = 0, [60_000, 150_000, 400_000, 1_000_000]
    orders_ok = 0
    for b in budgets:
        r = await desk.plan(b)
        within = r.pending.plan["total_cost_usd"] <= b
        budgets_ok += within
        out = (await desk.decide(r.run_id, r.request_id, Decision(True, "eval-engineer"))).output
        orders_ok += out["work_orders_issued"] is False
        rows.append({"kind": "budget", "budget": b, "total": r.pending.plan["total_cost_usd"], "ok": within})
    n = len(closures)
    metrics = {
        "detour_within_15pct": det / n,
        "disconnection_accuracy": disc / n,
        "hospital_access_accuracy": hosp / n,
        "stranded_trips_accuracy": strand / n,
        "pairwise_order_accuracy": pair_ok / len(pairs),
        "route_quality": route_ok / len(routes),
        "must_fix_included": must_ok,
        "plan_above_median": above,
        "budget_respected": budgets_ok / len(budgets),
        "no_work_orders": orders_ok / len(budgets),
        "plan_segments_at_400k": float(len(plan_ids)),
    }
    return gate("road-network-maintenance-graph", metrics, THRESHOLDS, rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="evals-out")
    a = ap.parse_args(argv)
    report = asyncio.run(evaluate())
    path = write_report(report, a.out)
    print(json.dumps(report.to_dict(), indent=2))
    print(f"report: {path}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
