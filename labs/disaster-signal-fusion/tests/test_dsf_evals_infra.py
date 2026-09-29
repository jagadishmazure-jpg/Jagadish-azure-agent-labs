import importlib.util
import json
from pathlib import Path

import pytest

from labcore.infra_check import build, find_bicep
from signal_fusion.card import CARD

LAB = Path(__file__).resolve().parents[1]


def _load_eval():
    spec = importlib.util.spec_from_file_location("dsf_eval", LAB / "evals" / "run_eval.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


async def test_eval_gate_passes():
    report = await _load_eval().evaluate()
    assert report.passed, report.failures


async def test_eval_catches_a_fusion_that_ignores_rain(monkeypatch):
    from signal_fusion import agents

    def deaf(self, weather):
        f = orig(self, weather)
        f.evidence["flood"]["weather"] = 0.0
        return f

    orig = agents.WeatherCorrelationAgent.analyse
    monkeypatch.setattr(agents.WeatherCorrelationAgent, "analyse", deaf)
    report = await _load_eval().evaluate()
    assert not report.passed
    assert report.metrics["signal_usage_rate"] < 1.0 and report.metrics["rain_sensitivity"] < 1.0


def test_agent_card_is_checked_in_and_current():
    path = LAB.parents[1] / "control-plane" / "agent-cards" / "disaster-signal-fusion.json"
    assert json.loads(path.read_text()) == CARD


@pytest.mark.skipif(find_bicep() is None, reason="bicep CLI not installed")
def test_bicep_compiles():
    res = build(LAB / "infra" / "main.bicep")
    assert res.returncode == 0, res.stderr
