from labcore.cards import agent_card
from legalcomp.classify import DENIED, DEPLOYMENT

CARD = agent_card(
    agent_id="legal-document-compliance",
    name="Contract and Policy Compliance Extractor",
    description="Parses banking, insurance and healthcare contracts and policies through reusable MCP tools into clause "
    "and table packets; a router picks the domain profile, a reliability agent scores OCR, an auditor can request one "
    "redo or escalate, and uncertain items go to a reviewer.",
    skills=[
        {
            "id": "review_document",
            "name": "Review document",
            "description": "Parse, extract, classify and score one document.",
            "tags": ["documents", "compliance"],
        },
        {
            "id": "record_reviewer_decision",
            "name": "Record reviewer decision",
            "description": "Accept or relabel clauses; nothing is written back to the contract system.",
            "tags": ["hitl"],
        },
    ],
    owner="legal-ops",
    model_deployment=DEPLOYMENT.name,
    data_zone=DEPLOYMENT.data_zone,
    side_effect_class="none (review packet only)",
    denied_tools=list(DENIED),
    eval_gate=[
        "clause_precision >= 0.95",
        "clause_recall >= 0.95",
        "label_accuracy >= 0.9",
        "tables_accounted >= 1.0",
        "junk_page_recall >= 1.0",
        "false_page_rejects <= 0",
        "audit_pass_rate >= 1.0",
        "compliance_checks_passed >= 1.0",
    ],
    human_review="compliance reviewer",
)
