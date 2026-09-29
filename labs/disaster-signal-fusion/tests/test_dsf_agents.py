"""Specialist agents and the Bayesian coordinator, tested without the workflow."""

import pytest

from signal_fusion.agents import (
    HistoricalPatternAgent,
    PredictionCoordinator,
    SatelliteMonitoringAgent,
    SeismicAnalysisAgent,
    TinyRecurrentPicker,
    VisionStandIn,
    WeatherCorrelationAgent,
    local_magnitude,
)
from signal_fusion.functions import FUNCTIONS
from signal_fusion.models import RawEvent
from signal_fusion.service import scenarios


def curated(scenario: str, source: str) -> dict:
    raw = next(r for r in scenarios()[scenario] if r["source"] == source)
    return FUNCTIONS[source](RawEvent.model_validate(raw)).model_dump()


def test_magnitude_recovered_from_seismogram():
    sig = curated("ridge-quake", "seismic")
    f = SeismicAnalysisAgent().analyse(sig, None, coastal=False)
    assert f.features["magnitude"] == pytest.approx(6.6, abs=0.05)
    assert f.features["pick_detected"] and f.features["pick_onset_index"] >= 19


def test_recurrent_picker_ignores_flat_noise():
    assert not TinyRecurrentPicker().run([0.001] * 64)["detected"]


def test_local_magnitude_monotonic_in_amplitude():
    assert local_magnitude(1e4, 50) > local_magnitude(1e3, 50)


def test_vision_standin_measures_water_and_ground_motion():
    sig = curated("ridge-quake", "satellite")["values"]
    img = VisionStandIn().analyze(sig["backscatter"], sig["interferogram_rad"], sig["wavelength_mm"])
    assert img["ground_disp_mm"] == pytest.approx(24.0, abs=0.5)
    assert img["water_extent_pct"] == pytest.approx(1.0)


def test_weather_agent_soil_moisture_amplifies_rain():
    base = curated("rain-only", "weather")
    wet = {**base, "values": {**base["values"], "soil_moisture_pct": 50.0}}
    a = WeatherCorrelationAgent().analyse(base).evidence["flood"]["weather"]
    b = WeatherCorrelationAgent().analyse(wet).evidence["flood"]["weather"]
    assert b > a > 0


def test_satellite_neighbour_fallback_is_half_weight():
    nb = curated("monsoon-flood", "satellite")
    f = SatelliteMonitoringAgent().analyse(None, coastal=False, neighbour=("harbor-delta", nb))
    assert f.fallbacks == {"satellite": "neighbour:harbor-delta"}
    assert f.weights["satellite"] == pytest.approx(nb["quality"] * 0.5)


def test_history_rag_filters_to_region_and_cites_ids():
    agent = HistoricalPatternAgent()
    hits = agent.analogs("harbor-delta", "Harbor Delta", "tsunami", 0.9)
    assert hits and all(h["record_id"].startswith("HIST-") for h in hits)
    assert all(agent.index.docs[h["record_id"]]["region_id"] == "harbor-delta" for h in hits)
    assert len(agent.index.docs) == 100  # fifty years x two records


def test_coordinator_missing_sensor_falls_back_to_prior_and_widens_uncertainty():
    w = WeatherCorrelationAgent().analyse(None)
    prior = {"flood": 0.1, "quake": 0.02, "tsunami": 0.001}
    rates = dict(prior)
    out = PredictionCoordinator().fuse(prior, [w], rates, coastal=False)
    assert out["fallbacks"]["weather"] == "prior"
    assert out["uncertainty"]["flood"] > 0.4
    assert out["posterior"]["flood"] == pytest.approx(0.1, abs=0.01)


def test_coordinator_drops_low_quality_sensor():
    sig = curated("rain-only", "weather")
    sig["quality"] = 0.1
    out = PredictionCoordinator().fuse(
        {"flood": 0.1, "quake": 0.02, "tsunami": 0.001},
        [WeatherCorrelationAgent().analyse(sig)],
        {"flood": 0.1, "quake": 0.02, "tsunami": 0.001},
        False,
    )
    assert "weather" not in out["contributions"]["flood"]
    assert out["fallbacks"]["weather"].startswith("prior")


def test_inland_region_has_no_tsunami_evidence():
    sig = curated("ridge-quake", "seismic")
    f = SeismicAnalysisAgent().analyse(sig, None, coastal=False)
    assert f.evidence["tsunami"] == {}
