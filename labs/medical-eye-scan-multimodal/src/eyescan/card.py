from eyescan.explainer import DENIED, DEPLOYMENT
from labcore.cards import agent_card

CARD = agent_card(
    agent_id="medical-eye-scan-multimodal",
    name="Retinal Scan Research Triage (NOT A MEDICAL DEVICE)",
    description="Research demo on synthetic arrays: image + metadata -> similar labeled cases -> calibrated, "
    "cited hypotheses for an ophthalmologist. Denies out-of-distribution scans; never writes to an EHR.",
    skills=[
        {
            "id": "triage_scan",
            "name": "Triage synthetic scan",
            "description": "Run the scan graph; returns hypotheses with cited case ids or a denial.",
            "tags": ["research", "multimodal"],
        },
        {
            "id": "record_review",
            "name": "Record reader review",
            "description": "Record the ophthalmologist's decision in the research log (not an EHR).",
            "tags": ["hitl"],
        },
    ],
    owner="imaging-research",
    model_deployment=DEPLOYMENT.name,
    data_zone=DEPLOYMENT.data_zone,
    side_effect_class="research-log only",
    denied_tools=list(DENIED),
    eval_gate=[
        "top1_accuracy >= 0.85",
        "ece <= 0.15",
        "ood_deny_rate >= 1.0",
        "false_deny_rate <= 0.05",
        "citation_validity >= 1.0",
        "ehr_writes <= 0",
    ],
    human_review="ophthalmologist",
)
