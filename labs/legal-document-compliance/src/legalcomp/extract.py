"""Deterministic parsing logic behind the MCP servers: layout lookup (Document Intelligence stand-in),
clause segmentation by numbered headings, and table normalisation."""

from __future__ import annotations

import json
import re

from legalcomp import DATA

HEADING = re.compile(r"^(\d+)\.\s+([A-Z][A-Z ,'&-]+)$")


def analyze_layout(doc_id: str) -> dict:
    path = DATA / "documents" / f"{doc_id}.json"
    if not path.exists():
        raise FileNotFoundError(doc_id)
    return json.loads(path.read_text())


def segment_clauses(doc_id: str, pages: list[dict], accepted_pages: list[int]) -> list[dict]:
    clauses: list[dict] = []
    cur: dict | None = None
    for p in pages:
        if p["page"] not in accepted_pages:
            cur = None  # never stitch a clause across a rejected page
            continue
        for ln in p["lines"][1:]:  # first line is the running title
            m = HEADING.match(ln["text"].strip())
            if m:
                cur = {
                    "clause_id": f"{doc_id}:s{m.group(1)}",
                    "section": int(m.group(1)),
                    "heading": m.group(2).strip(),
                    "lines": [],
                    "confs": [ln["confidence"]],
                    "pages": [p["page"]],
                }
                clauses.append(cur)
            elif cur is not None:
                cur["lines"].append(ln["text"])
                cur["confs"].append(ln["confidence"])
                if p["page"] not in cur["pages"]:
                    cur["pages"].append(p["page"])
    return [
        {
            "clause_id": c["clause_id"],
            "section": c["section"],
            "heading": c["heading"],
            "text": " ".join(c["lines"]),
            "pages": c["pages"],
            "ocr_confidence": round(sum(c["confs"]) / len(c["confs"]), 3),
        }
        for c in clauses
    ]


def normalise_tables(pages: list[dict], accepted_pages: list[int], min_conf: float = 0.8) -> dict:
    """Every table ends up in exactly one of `tables` or `needs_review`."""
    good, review = [], []
    for p in pages:
        for t in p["tables"]:
            widths = {len(r) for r in t["rows"]}
            if p["page"] not in accepted_pages:
                review.append(
                    {"table_id": t["table_id"], "page": p["page"], "reason": "page rejected for OCR quality"}
                )
            elif len(widths) != 1:
                review.append(
                    {
                        "table_id": t["table_id"],
                        "page": p["page"],
                        "reason": f"ragged rows (widths {sorted(widths)})",
                    }
                )
            elif t["confidence"] < min_conf:
                review.append(
                    {
                        "table_id": t["table_id"],
                        "page": p["page"],
                        "reason": f"low confidence {t['confidence']}",
                    }
                )
            else:
                good.append(
                    {
                        "table_id": t["table_id"],
                        "page": p["page"],
                        "header": t["rows"][0],
                        "rows": t["rows"][1:],
                        "confidence": t["confidence"],
                    }
                )
    return {"tables": good, "needs_review": review}
