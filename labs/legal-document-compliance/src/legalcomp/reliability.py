"""Reliability agent: scores each page for OCR junk and rejects pages that cannot be trusted.
A rejected page is reported (and its tables go to review); it is never quietly skipped."""

from __future__ import annotations

import re

WORD = re.compile(r"^[A-Za-z][a-z]*(?:[-'][a-z]+)?[.,;:]?$|^\d[\d,.%]*$|^[A-Z]{2,}[.,;:]?$")
SYMBOLS = set("~|#^%€?[]{}<>/\\@")
MAX_JUNK = 0.35
MIN_CONF = 0.6


def score_page(page: dict) -> dict:
    lines = page["lines"][1:] or page["lines"]
    toks = [t for ln in lines for t in ln["text"].split()]
    chars = "".join(ln["text"] for ln in lines)
    mean_conf = sum(ln["confidence"] for ln in lines) / len(lines)
    non_word = sum(1 for t in toks if not WORD.match(t)) / (len(toks) or 1)
    symbol = sum(1 for c in chars if c in SYMBOLS) / (len(chars) or 1)
    junk = round(0.45 * (1 - mean_conf) + 0.4 * non_word + 0.15 * min(1.0, symbol * 5), 3)
    accepted = junk <= MAX_JUNK and mean_conf >= MIN_CONF
    reason = (
        ""
        if accepted
        else (
            f"junk score {junk} > {MAX_JUNK}"
            if junk > MAX_JUNK
            else f"mean OCR confidence {mean_conf:.2f} < {MIN_CONF}"
        )
    )
    return {
        "page": page["page"],
        "mean_confidence": round(mean_conf, 3),
        "non_word_ratio": round(non_word, 3),
        "symbol_ratio": round(symbol, 3),
        "junk_score": junk,
        "accepted": accepted,
        "reason": reason,
    }
