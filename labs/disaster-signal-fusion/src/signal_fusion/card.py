from labcore.cards import agent_card
from signal_fusion.summary import DENIED, DEPLOYMENT

CARD = agent_card(
    agent_id="disaster-signal-fusion",
    name="Disaster Signal Fusion Desk",
    description="Fuses seismic, satellite, weather and ground-displacement signals into flood, earthquake "
    "and tsunami risk with decision support for a duty officer. Never issues public alerts.",
    skills=[
        {
            "id": "assess_region",
            "name": "Assess region",
            "description": "Run the fusion graph for one region; returns a review packet.",
            "tags": ["hazard", "fusion"],
        },
        {
            "id": "record_decision",
            "name": "Record officer decision",
            "description": "Record the duty officer's decision on the proposed warning review.",
            "tags": ["hitl"],
        },
    ],
    owner="public-safety-ops",
    model_deployment=DEPLOYMENT.name,
    data_zone=DEPLOYMENT.data_zone,
    side_effect_class="none (advice only)",
    denied_tools=list(DENIED),
    eval_gate=[
        "signal_usage_rate >= 1.0",
        "rain_sensitivity >= 1.0",
        "replay_hazard_accuracy >= 0.85",
        "no_public_alert >= 1.0",
    ],
    human_review="duty officer (alert decision)",
)
