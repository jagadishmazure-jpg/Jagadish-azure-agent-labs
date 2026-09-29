"""Plan narrative for the city engineer (Foundry, mocked). The model may reword the draft but the
segment list and total cost must match the computed plan exactly."""

from __future__ import annotations

from pydantic import BaseModel

from labcore.foundry import FoundryDeployment, FoundryWriter
from labcore.middleware import deny_tools

DEPLOYMENT = FoundryDeployment(
    "road-plan-narrative", model="gpt-5-mini", data_zone="us", purpose="plan narrative"
)
DENIED = ("*issue_work_order*", "*close_road*", "*dispatch*")


class PlanNarrative(BaseModel):
    title: str
    narrative: str
    segment_ids: list[str]
    total_cost_usd: float


def make_writer(client=None) -> FoundryWriter:
    return FoundryWriter(
        "plan-narrative",
        "Explain the maintenance plan to a city engineer in plain words. Use only the given plan.",
        PlanNarrative,
        DEPLOYMENT,
        client=client,
        middleware=[deny_tools(DENIED)],
    )


def draft(plan: dict) -> dict:
    lines = [
        f"Week {i['week']}: {i['name'] or i['segment_id']} ({i['method']}, ${i['cost_usd']:,})"
        for i in plan["items"]
    ]
    why = [
        f"{i['segment_id']} scores {i['score']} (usage {i['usage']}, criticality {i['criticality']}, potholes {i['potholes']})"
        for i in plan["items"][:3]
    ]
    return {
        "title": f"Repair plan: {len(plan['items'])} segments, ${plan['total_cost_usd']:,.0f} of ${plan['budget_usd']:,.0f}",
        "narrative": " ".join(lines)
        + ". Ranking drivers: "
        + "; ".join(why)
        + (f". Deferred: {', '.join(s['segment_id'] for s in plan['skipped'])}." if plan["skipped"] else "."),
        "segment_ids": [i["segment_id"] for i in plan["items"]],
        "total_cost_usd": plan["total_cost_usd"],
    }


def check_factory(plan: dict):
    ids = [i["segment_id"] for i in plan["items"]]

    def check(n: PlanNarrative) -> list[str]:
        p = []
        if n.segment_ids != ids:
            p.append("segment list differs from computed plan")
        if abs(n.total_cost_usd - plan["total_cost_usd"]) > 0.5:
            p.append("total cost differs from computed plan")
        return p

    return check
