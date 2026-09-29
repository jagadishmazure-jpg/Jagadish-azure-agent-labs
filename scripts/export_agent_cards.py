"""Render every lab's agent card into control-plane/agent-cards/.

python scripts/export_agent_cards.py          # write
python scripts/export_agent_cards.py --check  # exit 1 if a checked-in card is stale (CI)"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LABS = {
    "disaster-signal-fusion": "signal_fusion",
    "medical-eye-scan-multimodal": "eyescan",
    "road-network-maintenance-graph": "roadgraph",
    "legal-document-compliance": "legalcomp",
    "wind-turbine-continual-learning": "turbine_cl",
}


def cards() -> dict[str, dict]:
    sys.path[:0] = [str(ROOT / "shared")] + [str(ROOT / "labs" / lab / "src") for lab in LABS]
    out = {}
    for lab, pkg in LABS.items():
        if (ROOT / "labs" / lab / "src" / pkg / "card.py").exists():
            out[lab] = importlib.import_module(f"{pkg}.card").CARD
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    target = ROOT / "control-plane" / "agent-cards"
    target.mkdir(parents=True, exist_ok=True)
    stale = []
    for lab, card in cards().items():
        path = target / f"{lab}.json"
        text = json.dumps(card, indent=2, sort_keys=True) + "\n"
        if a.check:
            if not path.exists() or path.read_text() != text:
                stale.append(path.name)
        else:
            path.write_text(text)
    if stale:
        print("stale agent cards:", ", ".join(stale))
        return 1
    print("agent cards", "current" if a.check else "written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
