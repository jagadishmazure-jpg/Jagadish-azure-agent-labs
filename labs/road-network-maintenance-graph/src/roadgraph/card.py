from labcore.cards import agent_card
from roadgraph.narrative import DENIED, DEPLOYMENT

CARD = agent_card(
    agent_id="road-network-maintenance-graph",
    name="Road Maintenance Planner",
    description="Planning coordinator over graph engineering, graph features, maintenance priority and closure impact "
    "agents on a synthetic OSM-style city graph; commits a plan only within budget and hands it to a city engineer.",
    skills=[
        {
            "id": "plan_repairs",
            "name": "Plan repairs",
            "description": "Rank segments by need, usage and connectivity; select within budget.",
            "tags": ["graph", "planning"],
        },
        {
            "id": "record_engineer_decision",
            "name": "Record engineer decision",
            "description": "Approve, trim or return the plan.",
            "tags": ["hitl"],
        },
    ],
    owner="city-public-works",
    model_deployment=DEPLOYMENT.name,
    data_zone=DEPLOYMENT.data_zone,
    side_effect_class="none (plan only; no work orders)",
    denied_tools=list(DENIED),
    eval_gate=[
        "route_quality >= 1.0",
        "detour_within_15pct >= 1.0",
        "disconnection_accuracy >= 1.0",
        "hospital_access_accuracy >= 1.0",
        "pairwise_order_accuracy >= 1.0",
        "must_fix_included >= 1.0",
        "budget_respected >= 1.0",
    ],
    human_review="city engineer",
)
