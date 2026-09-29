"""Eval gate for the legal/compliance lab: clause ids must match the gold set.

    python labs/legal-document-compliance/evals/run_eval.py [--out evals-out]

* clause_precision / clause_recall: compliance clause ids (label != other) vs gold, pooled over documents
* label_accuracy: share of matched clause ids with the gold label
* tables_accounted: every parsed table is either extracted or queued for review
* junk_page_recall / false_page_rejects: the badly scanned page is rejected, clean pages are not
* audit_pass_rate / compliance_checks_passed: output reliability - the auditor accepted the clauses
  without escalation and each document holds the clause types its domain requires
* mean_ocr_confidence / mean_uncertainty: document quality and uncertainty, reported per run
* per-domain precision/recall is reported (banking, insurance, healthcare)"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "src"), str(HERE.parents[2] / "shared")]

from labcore.evals import Threshold, gate, load_jsonl, precision_recall, write_report  # noqa: E402
from legalcomp.extract import analyze_layout  # noqa: E402
from legalcomp.service import ComplianceDesk  # noqa: E402

THRESHOLDS = [
    Threshold("clause_precision", ">=", 0.95),
    Threshold("clause_recall", ">=", 0.95),
    Threshold("label_accuracy", ">=", 0.9),
    Threshold("tables_accounted", ">=", 1.0),
    Threshold("junk_page_recall", ">=", 1.0),
    Threshold("false_page_rejects", "<=", 0),
    Threshold("audit_pass_rate", ">=", 1.0),
    Threshold("compliance_checks_passed", ">=", 1.0),
]


async def evaluate():
    logging.getLogger("agent_framework").setLevel(logging.WARNING)
    desk = ComplianceDesk()
    rows, pred_all, gold_all = [], set(), set()
    labels_ok = matched = tables_ok = n_docs = junk_hit = junk_n = false_rej = audits_ok = checks_ok = 0
    confs, uncs = [], []
    by_domain: dict[str, tuple[set, set]] = {}
    for g in load_jsonl(HERE / "gold" / "clauses.jsonl"):
        res = await desk.review(g["doc_id"])
        p = res.pending
        pred = {c["clause_id"]: c["label"] for c in p.clauses}
        gold = {c["clause_id"]: c["label"] for c in g["clauses"]}
        pred_all |= set(pred)
        gold_all |= set(gold)
        d = by_domain.setdefault(g["domain"], (set(), set()))
        d[0].update(pred)
        d[1].update(gold)
        for cid in set(pred) & set(gold):
            matched += 1
            labels_ok += pred[cid] == gold[cid]
        parsed = {t["table_id"] for pg in analyze_layout(g["doc_id"])["pages"] for t in pg["tables"]}
        accounted = {t["table_id"] for t in p.tables} | {t["table_id"] for t in p.tables_for_review}
        tables_ok += parsed == accounted
        n_docs += 1
        junk_n += len(g["rejected_pages"])
        junk_hit += len(set(g["rejected_pages"]) & set(p.rejected_pages))
        false_rej += len(set(p.rejected_pages) - set(g["rejected_pages"]))
        audits_ok += p.audit["action"] == "pass"
        checks_ok += not p.audit["missing_required"]
        confs += [c["ocr_confidence"] for c in p.clauses]
        uncs.append(p.uncertainty)
        pr, rc = precision_recall(pred, gold)
        rows.append(
            {
                "doc": g["doc_id"],
                "precision": pr,
                "recall": rc,
                "missing": sorted(set(gold) - set(pred)),
                "extra": sorted(set(pred) - set(gold)),
                "rejected_pages": p.rejected_pages,
            }
        )
    precision, recall = precision_recall(pred_all, gold_all)
    metrics = {
        "clause_precision": precision,
        "clause_recall": recall,
        "label_accuracy": labels_ok / (matched or 1),
        "tables_accounted": tables_ok / n_docs,
        "junk_page_recall": junk_hit / (junk_n or 1),
        "false_page_rejects": float(false_rej),
        "audit_pass_rate": audits_ok / n_docs,
        "compliance_checks_passed": checks_ok / n_docs,
        "mean_ocr_confidence": sum(confs) / (len(confs) or 1),
        "mean_uncertainty": sum(uncs) / n_docs,
    }
    for dom, (pp, gg) in sorted(by_domain.items()):
        metrics[f"{dom}_precision"], metrics[f"{dom}_recall"] = precision_recall(pp, gg)
    return gate("legal-document-compliance", metrics, THRESHOLDS, rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="evals-out")
    a = ap.parse_args(argv)
    report = asyncio.run(evaluate())
    path = write_report(report, a.out)
    print(json.dumps(report.to_dict(), indent=2))
    print(f"report: {path}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
