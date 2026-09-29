"""Budget harness. The coordinator may only commit a plan through `BudgetGuard`, which enforces the
money budget, a worker-call budget and the staging rule that two river bridges are never closed in
the same week. Violations raise instead of being silently trimmed."""

from __future__ import annotations

from dataclasses import dataclass, field


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class BudgetGuard:
    budget_usd: float
    max_worker_calls: int = 12
    worker_calls: int = 0
    committed_usd: float = 0.0
    ledger: list[dict] = field(default_factory=list)

    def worker(self, name: str) -> None:
        self.worker_calls += 1
        if self.worker_calls > self.max_worker_calls:
            raise BudgetExceeded(f"worker budget {self.max_worker_calls} exceeded at {name}")

    def commit(self, item: dict) -> None:
        if self.committed_usd + item["cost_usd"] > self.budget_usd + 1e-6:
            raise BudgetExceeded(
                f"{item['segment_id']}: ${item['cost_usd']:,} would exceed budget ${self.budget_usd:,.0f}"
            )
        self.committed_usd += item["cost_usd"]
        self.ledger.append({"segment_id": item["segment_id"], "cost_usd": item["cost_usd"]})

    @property
    def remaining(self) -> float:
        return self.budget_usd - self.committed_usd


def select_plan(
    ranked: list[dict], impacts: dict[str, dict], guard: BudgetGuard, min_score: float = 0.05
) -> dict:
    """Greedy by priority; skip items that do not fit (recorded, not hidden). Closures that strand
    critical trips get night/lane-open work; bridges go in different weeks."""
    plan, skipped, week, bridge_weeks = [], [], 1, set()
    for r in ranked:
        if r["score"] < min_score:
            break
        if r["segment_id"] not in impacts:
            skipped.append({"segment_id": r["segment_id"], "reason": "no closure impact simulated"})
            continue
        if r["cost_usd"] > guard.remaining:
            skipped.append({"segment_id": r["segment_id"], "reason": "does not fit remaining budget"})
            continue
        guard.commit(r)
        imp = impacts[r["segment_id"]]
        method = (
            "night work, one lane open"
            if imp["critical_trips_stranded"] or imp["hospital_access_lost"]
            else (
                "full closure with signed detour" if imp["extra_vehicle_minutes"] < 800 else "weekend closure"
            )
        )
        w = week
        if r["bridge"]:
            while w in bridge_weeks:
                w += 1
            bridge_weeks.add(w)
        plan.append({**r, "week": w, "method": method, "impact": imp})
        week += 1
    return {
        "items": plan,
        "skipped": skipped,
        "total_cost_usd": guard.committed_usd,
        "budget_usd": guard.budget_usd,
    }
