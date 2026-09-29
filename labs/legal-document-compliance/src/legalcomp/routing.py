"""Router and auditor agents.

Router: reads the parsed layout, decides the domain profile from the text itself (and flags a
mismatch with the declared domain), and hands rejected pages straight to the escalation queue.

Auditor: checks the classified clauses and either passes them on, asks the classifier to redo
specific clauses once (regeneration, on the second deployment), or escalates to the reviewer.
It also runs the domain compliance checklist (required clause types per document kind)."""

from __future__ import annotations

from legalcomp.classify import TAXONOMY

DOMAIN_TERMS = {
    "banking": ["borrower", "lender", "loan", "due diligence", "sanctions", "member account", "credit union"],
    "insurance": ["policy", "insure", "claim", "deductible", "premium", "adjuster"],
    "healthcare": ["health information", "patient", "clinic", "breach", "business associate"],
}
REQUIRED = {  # clause types a reviewer expects to see, by domain
    "banking": {"kyc_aml"},
    "insurance": {"claims_notice"},
    "healthcare": {"data_protection", "breach_notification"},
}
MAX_REDO = 1
MIN_MARGIN = 0.25


def route(layout: dict, reliability: list[dict]) -> dict:
    text = " ".join(ln["text"].lower() for p in layout["pages"] for ln in p["lines"])
    hits = {d: sum(text.count(t) for t in terms) for d, terms in DOMAIN_TERMS.items()}
    detected = max(hits, key=lambda d: hits[d])
    return {
        "declared_domain": layout["domain"],
        "detected_domain": detected,
        "domain_scores": hits,
        "mismatch": detected != layout["domain"],
        "profile": f"{detected}-clauses-v1",
        "escalated_pages": [r["page"] for r in reliability if not r["accepted"]],
    }


def audit(classified: list[dict], domain: str, redo_count: int) -> dict:
    """Returns {"action": "pass" | "redo" | "escalate", "redo_ids": [...], "findings": [...]}."""
    findings, suspects = [], []
    for c in classified:
        if c["label"] not in TAXONOMY:
            suspects.append(c["clause_id"])
            findings.append(f"{c['clause_id']}: label outside taxonomy")
        elif not c["model_agrees"]:
            suspects.append(c["clause_id"])
            findings.append(
                f"{c['clause_id']}: model label {c['label']} disagrees with rule label {c['rule_label']}"
            )
        elif c["label"] != "other" and c["margin"] < MIN_MARGIN:
            findings.append(f"{c['clause_id']}: weak margin {c['margin']}")
    present = {c["label"] for c in classified}
    missing = sorted(REQUIRED.get(domain, set()) - present)
    findings += [f"compliance check: no {m} clause found for a {domain} document" for m in missing]
    if suspects and redo_count < MAX_REDO:
        return {"action": "redo", "redo_ids": suspects, "findings": findings, "missing_required": missing}
    if suspects:
        return {
            "action": "escalate",
            "redo_ids": [],
            "findings": findings,
            "missing_required": missing,
            "escalated_clauses": suspects,
        }
    return {"action": "pass", "redo_ids": [], "findings": findings, "missing_required": missing}
