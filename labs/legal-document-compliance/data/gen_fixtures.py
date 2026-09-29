"""Synthetic contracts and policies in a Document Intelligence "layout"-like shape (pages, lines with
OCR confidence, tables). All parties, terms and numbers are invented.

    python data/gen_fixtures.py

Writes data/documents/<doc_id>.json and the gold set evals/gold/clauses.jsonl."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).parent
GOLD = HERE.parent / "evals" / "gold"


def conf(key: str, lo: float = 0.93, hi: float = 0.995) -> float:
    h = int(hashlib.md5(key.encode()).hexdigest()[:6], 16) / 0xFFFFFF
    return round(lo + (hi - lo) * h, 3)


# doc_id -> (domain, title, pages); each page: list of ("S", n, heading, label, [body lines]) or ("T", id, rows)
DOCS = {
    "bank-term-loan": (
        "banking",
        "Term Loan Facility Agreement - Northwind Credit Union and Alder Tools Ltd",
        [
            [
                (
                    "S",
                    1,
                    "DEFINITIONS",
                    None,
                    [
                        "In this agreement Borrower means Alder Tools Ltd and Lender means Northwind Credit Union.",
                        "Business Day means a day banks in the governing jurisdiction are open.",
                    ],
                ),
                (
                    "S",
                    2,
                    "INTEREST AND REPAYMENT",
                    "payment_terms",
                    [
                        "The Borrower shall pay interest monthly in arrears at the rate in the schedule below.",
                        "Each instalment is due on the fifth Business Day of the month; late amounts accrue default interest of 2 percent.",
                    ],
                ),
                (
                    "T",
                    "repayment-schedule",
                    [
                        ["Instalment", "Due month", "Principal (USD)"],
                        ["1", "2026-01", "25,000"],
                        ["2", "2026-02", "25,000"],
                        ["3", "2026-03", "25,000"],
                    ],
                ),
            ],
            [
                (
                    "S",
                    3,
                    "EVENTS OF DEFAULT AND TERMINATION",
                    "termination",
                    [
                        "The Lender may terminate the facility and demand repayment if an instalment is unpaid for 30 days.",
                        "Insolvency of the Borrower is an immediate event of default.",
                    ],
                ),
                (
                    "S",
                    4,
                    "KNOW YOUR CUSTOMER AND ANTI-MONEY LAUNDERING",
                    "kyc_aml",
                    [
                        "The Borrower shall provide beneficial ownership information and identity documents on request.",
                        "The Lender may suspend drawdowns while sanctions screening is pending.",
                    ],
                ),
                (
                    "S",
                    5,
                    "CONFIDENTIALITY",
                    "confidentiality",
                    [
                        "Each party shall keep the terms of this agreement confidential and disclose them only to advisers bound by similar duties."
                    ],
                ),
                (
                    "S",
                    6,
                    "GOVERNING LAW",
                    "governing_law",
                    [
                        "This agreement is governed by the laws of the State of New York and the parties submit to its courts."
                    ],
                ),
            ],
        ],
    ),
    "bank-kyc-policy": (
        "banking",
        "Customer Due Diligence Policy - Northwind Credit Union",
        [
            [
                (
                    "S",
                    1,
                    "PURPOSE",
                    None,
                    [
                        "This policy sets the minimum steps staff follow before opening or reviewing a member account."
                    ],
                ),
                (
                    "S",
                    2,
                    "CUSTOMER DUE DILIGENCE",
                    "kyc_aml",
                    [
                        "Staff verify identity, screen against sanctions lists and record the source of funds for every new member.",
                        "Enhanced due diligence applies to politically exposed persons and high-risk jurisdictions.",
                    ],
                ),
                (
                    "T",
                    "risk-tiers",
                    [
                        ["Tier", "Review cycle", "Approver"],
                        ["Low", "36 months", "Branch lead"],
                        ["Medium", "12 months", "Compliance analyst"],
                        ["High", "6 months", "BSA officer"],
                    ],
                ),
            ],
            [
                (
                    "S",
                    3,
                    "RECORD RETENTION AND PRIVACY",
                    "data_protection",
                    [
                        "Identity records are retained for five years after the account closes and then securely destroyed.",
                        "Personal data is processed only for due diligence and regulatory reporting.",
                    ],
                ),
                (
                    "S",
                    4,
                    "INTERNAL AUDIT",
                    "audit_rights",
                    [
                        "Internal audit tests a sample of files each quarter and may inspect any record without notice."
                    ],
                ),
            ],
        ],
    ),
    "ins-property-wording": (
        "insurance",
        "Commercial Property Policy Wording - Harbourline Mutual",
        [
            [
                (
                    "S",
                    1,
                    "COVER",
                    None,
                    [
                        "We insure the buildings and contents listed in the schedule against sudden physical loss or damage."
                    ],
                ),
                (
                    "S",
                    2,
                    "EXCLUSIONS",
                    "exclusions",
                    [
                        "We do not pay for loss caused by wear and tear, gradual pollution, or war.",
                        "Flood is excluded unless the schedule shows the flood extension.",
                    ],
                ),
                (
                    "S",
                    3,
                    "CLAIMS NOTIFICATION",
                    "claims_notice",
                    [
                        "You must tell us about any loss within 14 days and send supporting invoices within 60 days.",
                        "Late notice may reduce what we pay if it harmed our ability to investigate.",
                    ],
                ),
            ],
            [
                (
                    "S",
                    4,
                    "LIMITS OF LIABILITY",
                    "limitation_of_liability",
                    [
                        "Our total liability in any period of insurance will not exceed the limits in the table below."
                    ],
                ),
                (
                    "T",
                    "limits",
                    [
                        ["Section", "Limit (USD)", "Deductible (USD)"],
                        ["Buildings", "5,000,000", "10,000"],
                        ["Contents", "1,500,000", "5,000"],
                        ["Business interruption", "750,000", "72 hours"],
                    ],
                ),
                (
                    "S",
                    5,
                    "CANCELLATION",
                    "termination",
                    [
                        "Either party may cancel this policy with 30 days written notice; unused premium is refunded pro rata."
                    ],
                ),
            ],
        ],
    ),
    "ins-claims-standard": (
        "insurance",
        "Claims Handling Standard - Harbourline Mutual",
        [
            [
                (
                    "S",
                    1,
                    "SCOPE",
                    None,
                    [
                        "This standard applies to every first-party property claim handled in house or by a delegated adjuster."
                    ],
                ),
                (
                    "S",
                    2,
                    "FIRST NOTICE AND ACKNOWLEDGEMENT",
                    "claims_notice",
                    ["Every notice of loss is acknowledged within two business days and assigned a handler."],
                ),
                (
                    "T",
                    "service-levels",
                    [
                        ["Step", "Target", "Escalation"],
                        ["Acknowledge", "2 days", "Team lead"],
                        ["Site visit", "5 days", "Claims manager"],
                        ["Settlement offer", "30 days", "Head of claims"],
                    ],
                ),
            ],
            [
                (
                    "S",
                    3,
                    "DELEGATED AUTHORITY AUDITS",
                    "audit_rights",
                    ["Harbourline may audit any delegated adjuster's files on ten days notice."],
                ),
                (
                    "S",
                    4,
                    "INDEMNITY FOR ADJUSTER ERRORS",
                    "indemnification",
                    [
                        "A delegated adjuster indemnifies Harbourline for losses caused by its negligent handling."
                    ],
                ),
            ],
        ],
    ),
    "hc-business-associate": (
        "healthcare",
        "Business Associate Agreement - Cedar Valley Clinics and Brightline Billing",
        [
            [
                (
                    "S",
                    1,
                    "PERMITTED USES OF PROTECTED HEALTH INFORMATION",
                    "data_protection",
                    [
                        "Brightline may use protected health information only to perform billing services for Cedar Valley.",
                        "Brightline applies administrative, physical and technical safeguards to that information.",
                    ],
                ),
                (
                    "S",
                    2,
                    "BREACH NOTIFICATION",
                    "breach_notification",
                    [
                        "Brightline reports any breach of unsecured information to Cedar Valley without unreasonable delay and within 10 days of discovery."
                    ],
                ),
            ],
            [
                (
                    "S",
                    3,
                    "AUDIT AND INSPECTION",
                    "audit_rights",
                    [
                        "Cedar Valley may inspect Brightline's safeguards and records once a year or after a breach."
                    ],
                ),
                (
                    "S",
                    4,
                    "TERM AND TERMINATION",
                    "termination",
                    [
                        "Cedar Valley may terminate this agreement if Brightline materially breaches it and does not cure within 30 days."
                    ],
                ),
                (
                    "S",
                    5,
                    "INDEMNIFICATION",
                    "indemnification",
                    [
                        "Brightline indemnifies Cedar Valley against penalties arising from Brightline's violation of this agreement."
                    ],
                ),
            ],
            "JUNK",  # a badly scanned appendix page with a fee table on it
        ],
    ),
    "hc-privacy-notice": (
        "healthcare",
        "Patient Privacy Practices - Cedar Valley Clinics",
        [
            [
                (
                    "S",
                    1,
                    "HOW WE USE YOUR INFORMATION",
                    "data_protection",
                    [
                        "We use your health information to treat you, to get paid, and to run our clinics.",
                        "We do not sell your information.",
                    ],
                ),
                (
                    "S",
                    2,
                    "IF YOUR INFORMATION IS EXPOSED",
                    "breach_notification",
                    ["If a breach affects your information we will notify you in writing within 60 days."],
                ),
                (
                    "T",
                    "retention",
                    [
                        ["Record type", "Kept for"],
                        ["Adult chart", "10 years"],
                        ["Minor chart", "Until age 28"],
                        ["Billing", "7 years", "extra"],
                    ],
                ),
            ],  # ragged row on purpose
            [
                (
                    "S",
                    3,
                    "CHANGES TO THIS NOTICE",
                    None,
                    ["We may change this notice and will post the new version in every clinic."],
                ),
                (
                    "S",
                    4,
                    "GOVERNING LAW",
                    "governing_law",
                    ["This notice is interpreted under the laws of the State of Oregon."],
                ),
            ],
        ],
    ),
}
JUNK_LINES = [
    "Appx B ~~ F3e sch3du|e /// ##",
    "l1ne 1tem ;; cod3 .. ^^ %%",
    "Sch#d Fe€ ||| ??? 0O0O",
    "~~~ ::: [[ ]] ###",
]


def build_doc(doc_id: str) -> tuple[dict, list[dict], list[int]]:
    domain, title, pages = DOCS[doc_id]
    out_pages, gold, junk_pages = [], [], []
    for pno, page in enumerate(pages, start=1):
        lines, tables = [{"text": title if pno == 1 else f"{title} - page {pno}", "confidence": 0.99}], []
        if page == "JUNK":
            junk_pages.append(pno)
            lines += [{"text": t, "confidence": conf(f"{doc_id}{pno}{t}", 0.31, 0.55)} for t in JUNK_LINES]
            tables.append(
                {
                    "table_id": f"{doc_id}:t-fees",
                    "confidence": 0.42,
                    "rows": [["Cod3", "F€e"], ["B1", "1O0"], ["B2", "2?0"]],
                }
            )
        else:
            for item in page:
                if item[0] == "S":
                    _, n, heading, label, body = item
                    lines.append({"text": f"{n}. {heading}", "confidence": conf(f"{doc_id}{n}h")})
                    lines += [{"text": t, "confidence": conf(f"{doc_id}{n}{t}")} for t in body]
                    if label:
                        gold.append({"clause_id": f"{doc_id}:s{n}", "label": label})
                else:
                    _, tid, rows = item
                    tables.append(
                        {"table_id": f"{doc_id}:t-{tid}", "confidence": conf(tid, 0.9, 0.98), "rows": rows}
                    )
        out_pages.append({"page": pno, "lines": lines, "tables": tables})
    return {"doc_id": doc_id, "domain": domain, "title": title, "pages": out_pages}, gold, junk_pages


if __name__ == "__main__":
    GOLD.mkdir(parents=True, exist_ok=True)
    (HERE / "documents").mkdir(exist_ok=True)
    rows = []
    for d in DOCS:
        doc, gold, junk = build_doc(d)
        (HERE / "documents" / f"{d}.json").write_text(json.dumps(doc, indent=1) + "\n")
        rows.append(
            {
                "doc_id": d,
                "domain": doc["domain"],
                "clauses": gold,
                "rejected_pages": junk,
                "tables": [t["table_id"] for p in doc["pages"] for t in p["tables"]],
            }
        )
    (GOLD / "clauses.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    print(f"{len(rows)} documents written")
