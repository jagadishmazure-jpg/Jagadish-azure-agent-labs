"""Vision stand-in, RAG, OOD gate, reasoning and calibration."""

import json

import pytest

from eyescan import DATA, LABELS
from eyescan.knowledge import OodGate
from eyescan.reasoning import fit_temperature, metadata_prior, softmax
from eyescan.service import shared_models
from eyescan.vision import VisionStandIn

GOLD = DATA.parent / "evals" / "gold"


def case(cid: str) -> dict:
    for f in (GOLD / "test_cases.json", GOLD / "ood_cases.json", DATA / "library.json"):
        for c in json.loads(f.read_text()):
            if c["case_id"] == cid:
                return c
    raise KeyError(cid)


def test_fixtures_are_tiny_synthetic_arrays():
    lib = json.loads((DATA / "library.json").read_text())
    assert len(lib) == 40 and all(len(c["image"]) == 16 and len(c["image"][0]) == 16 for c in lib)
    assert {c["label"] for c in lib} == set(LABELS)


def test_vision_features_separate_glaucoma_cup():
    v = VisionStandIn()
    g = v.features(case("TES-018")["image"])
    n = v.features(case("TES-001")["image"])
    assert g["cup_ratio"] > n["cup_ratio"]


def test_vision_rejects_wrong_shape():
    with pytest.raises(ValueError):
        VisionStandIn().features([[0.1] * 8] * 8)


def test_hybrid_retrieval_returns_labeled_cases():
    lib, _ = shared_models()
    c = case("TES-025")
    hits = lib.similar(lib.embed(lib.vision.features(c["image"])), c["metadata"])
    assert len(hits) == 5 and all(h["case_id"].startswith("LIB-") for h in hits)
    assert hits[0]["label"] == "amd"


def test_reference_reports_are_retrieved_per_label():
    lib, _ = shared_models()
    refs = lib.references(["glaucoma", "normal"], "cup")
    assert [r["ref_id"] for r in refs] == ["REF-GL-01", "REF-N-01"]


def test_ood_gate_reasons():
    gate = OodGate()
    scan = case("OOD-003")
    feats = VisionStandIn().features(scan["image"])
    assert "modality" in gate.check(scan, 0.1, 1.0, feats)["reasons"][0]


def test_metadata_prior_is_small_nudge():
    p = metadata_prior({"diabetes": True, "iop_mmHg": 40, "age": 90})
    assert max(p.values()) <= 0.8


def test_temperature_fit_prefers_softer_when_overconfident():
    rows = [({"a": 5.0, "b": 0.0}, "b"), ({"a": 5.0, "b": 0.0}, "a")]
    assert fit_temperature(rows) > 2


def test_calibrated_probabilities_sum_to_one():
    _, r = shared_models()
    assert r.calibrated and 0.2 <= r.temperature <= 6
    assert sum(softmax({"a": 1, "b": 2}, r.temperature).values()) == pytest.approx(1.0)


def test_constrained_hypotheses_need_retrieved_support():
    _, r = shared_models()
    hyps, _ = r.hypotheses(
        [{"case_id": "LIB-001", "label": "normal", "distance": 0.5}],
        {"diabetes": True, "iop_mmHg": 30, "age": 70},
        {"cup_ratio": 0, "specks": 0, "dark_dots": 0, "macula_specks": 0},
    )
    assert [h["label"] for h in hyps] == ["normal"]
    assert hyps[0]["supporting_cases"] == ["LIB-001"]


def test_abstains_when_evidence_is_split():
    _, r = shared_models()
    similar = [{"case_id": f"L{i}", "label": lab, "distance": 1.0} for i, lab in enumerate(LABELS)]
    _, abstain = r.hypotheses(
        similar,
        {"diabetes": False, "iop_mmHg": 15, "age": 60},
        {"cup_ratio": 0, "specks": 0, "dark_dots": 0, "macula_specks": 0},
    )
    assert abstain
