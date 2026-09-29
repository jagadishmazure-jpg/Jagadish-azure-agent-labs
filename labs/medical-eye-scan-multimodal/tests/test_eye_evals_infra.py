import importlib.util
import json
from pathlib import Path

import pytest

from eyescan.card import CARD
from labcore.infra_check import build, find_bicep

LAB = Path(__file__).resolve().parents[1]


def _eval():
    spec = importlib.util.spec_from_file_location("eye_eval", LAB / "evals" / "run_eval.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


async def test_eval_gate_passes():
    rep = await _eval().evaluate()
    assert rep.passed, rep.failures


async def test_gate_fails_if_ood_gate_disabled(monkeypatch):
    from eyescan import knowledge

    monkeypatch.setattr(knowledge.OodGate, "check", lambda self, *a, **k: {"denied": False, "reasons": []})
    rep = await _eval().evaluate()
    assert rep.metrics["ood_deny_rate"] == 0.0 and not rep.passed


def test_readme_has_banner_first():
    first = (LAB / "README.md").read_text().splitlines()[0:6]
    assert any("NOT A MEDICAL DEVICE" in line for line in first)


def test_agent_card_current():
    path = LAB.parents[1] / "control-plane" / "agent-cards" / "medical-eye-scan-multimodal.json"
    assert json.loads(path.read_text()) == CARD


@pytest.mark.skipif(find_bicep() is None, reason="bicep CLI not installed")
def test_bicep_compiles():
    res = build(LAB / "infra" / "main.bicep")
    assert res.returncode == 0, res.stderr
