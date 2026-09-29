"""Clause classification. A lexicon scorer over heading + body gives a label and a margin; the
Foundry classifier (mocked) may only pick a label from the taxonomy, and its answer is checked.
Clauses labelled `other` (definitions, scope, purpose...) are not compliance clauses."""

from __future__ import annotations

import re

from labcore.foundry import FoundryDeployment, FoundryWriter
from labcore.middleware import deny_tools
from legalcomp.models import ClauseClassification

DEPLOYMENT = FoundryDeployment(
    "clause-classifier", model="gpt-5-mini", data_zone="us", purpose="clause classification"
)
REDO_DEPLOYMENT = FoundryDeployment(
    "clause-classifier-redo", model="gpt-5", data_zone="us", purpose="auditor-requested redo"
)
DENIED = ("*sign*", "*execute_contract*", "*send_to_counterparty*", "*delete*")

LEXICON: dict[str, list[str]] = {
    "payment_terms": ["interest", "instalment", "repayment", "arrears", "pay", "due"],
    "termination": ["terminate", "termination", "cancel", "cancellation", "default", "cure"],
    "kyc_aml": [
        "know your customer",
        "anti-money",
        "beneficial ownership",
        "sanctions",
        "due diligence",
        "identity",
    ],
    "confidentiality": ["confidential", "confidentiality", "disclose"],
    "governing_law": ["governing law", "governed by", "laws of the state", "interpreted under", "courts"],
    "data_protection": [
        "personal data",
        "health information",
        "privacy",
        "safeguards",
        "retained",
        "use your",
    ],
    "breach_notification": ["breach", "notify", "exposed", "reports any breach"],
    "audit_rights": ["audit", "inspect", "inspection"],
    "exclusions": ["exclusion", "excluded", "we do not pay"],
    "claims_notice": ["claim", "notice of loss", "tell us about any loss", "acknowledged"],
    "limitation_of_liability": ["limit of liability", "limits of liability", "total liability", "not exceed"],
    "indemnification": ["indemnif", "indemnity"],
}
TAXONOMY = (*LEXICON, "other")
HEADING_WEIGHT = 3.0


def score(heading: str, text: str) -> dict[str, float]:
    h, b = heading.lower(), text.lower()
    out = {}
    for label, terms in LEXICON.items():
        out[label] = sum(
            HEADING_WEIGHT * len(re.findall(re.escape(t), h)) + len(re.findall(re.escape(t), b))
            for t in terms
        )
    return out


def rule_label(heading: str, text: str) -> tuple[str, float]:
    """(label, margin in [0, 1]). Margin = (best - second) / best; `other` when nothing scores >= 2."""
    s = score(heading, text)
    ranked = sorted(s.items(), key=lambda kv: (-kv[1], kv[0]))
    (best, b), (_, second) = ranked[0], ranked[1]
    if b < 2:
        return "other", 1.0 - b / 2
    return best, round((b - second) / b, 3)


def make_writer(client=None, *, redo: bool = False) -> FoundryWriter:
    extra = " An auditor rejected the previous label; re-read the heading and body carefully." if redo else ""
    return FoundryWriter(
        "clause-classifier-redo" if redo else "clause-classifier",
        f"Classify the clause into exactly one label from: {', '.join(TAXONOMY)}. Give a one-line rationale.{extra}",
        ClauseClassification,
        REDO_DEPLOYMENT if redo else DEPLOYMENT,
        client=client,
        middleware=[deny_tools(DENIED)],
    )


def check_factory(clause_id: str):
    def check(c: ClauseClassification) -> list[str]:
        p = []
        if c.label not in TAXONOMY:
            p.append(f"label {c.label!r} not in taxonomy")
        if c.clause_id != clause_id:
            p.append("clause id changed")
        return p

    return check
