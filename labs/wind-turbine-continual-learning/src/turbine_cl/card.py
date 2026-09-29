from labcore.cards import agent_card
from turbine_cl.diagnose import DENIED, DEPLOYMENT

CARD = agent_card(
    agent_id="wind-turbine-continual-learning",
    name="Turbine Diagnostics with Continual Learning",
    description="Static maintenance (Isolation Forest + pattern rules), episodic memory, context-gated lessons, "
    "evaluation, learning signals and candidate-lesson extraction for wind turbines; technician-confirmed episodes "
    "become memory. Detector and lesson promotion are separate eval-gated pipelines, not agent skills.",
    skills=[
        {
            "id": "check_turbine",
            "name": "Check turbine window",
            "description": "Detect, retrieve, diagnose and recommend for one turbine.",
            "tags": ["telemetry", "anomaly"],
        },
        {
            "id": "record_technician_decision",
            "name": "Record technician decision",
            "description": "Confirm, correct or reject; evaluates the outcome, emits a learning signal and a "
            "candidate lesson, and writes the episode to memory.",
            "tags": ["hitl"],
        },
    ],
    owner="fleet-reliability",
    model_deployment=DEPLOYMENT.name,
    data_zone=DEPLOYMENT.data_zone,
    side_effect_class="episode memory + candidate lesson write after HITL",
    denied_tools=list(DENIED),
    eval_gate=[
        "heldout_recall >= 0.9",
        "heldout_fpr <= 0.1",
        "diagnosis_accuracy >= 0.85",
        "bad_candidates_rejected >= 1.0",
        "registry_unchanged_by_agents >= 1.0",
        "lesson_learned_from_feedback >= 1.0",
        "overbroad_lesson_rejected >= 1.0",
        "lesson_gain >= 0.1",
        "gating_precision >= 1.0",
        "safer_decision_after_learning >= 1.0",
    ],
    human_review="turbine technician",
)
