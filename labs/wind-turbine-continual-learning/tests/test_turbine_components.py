"""Features, detectors, registry, episode memory, diagnosis and the promotion pipeline."""

import json
import shutil

import numpy as np
import pytest

from turbine_cl import DATA, REGISTRY
from turbine_cl.detector import (
    DetectorRegistry,
    RegistryError,
    ZScoreDetector,
    make_detector,
    score_window,
    train_rows,
)
from turbine_cl.diagnose import CATALOG, diagnose
from turbine_cl.episodes import EpisodeStore
from turbine_cl.features import FEATURES, matrix, residuals
from turbine_cl.promotion import evaluate_detector, promote

SCEN = json.loads((DATA / "stream_scenarios.json").read_text())


@pytest.fixture(scope="module")
def champion():
    return DetectorRegistry().load_champion()


def test_residuals_near_zero_for_healthy_rows():
    x = matrix(train_rows("normal_train.json"))
    assert x.shape[1] == len(FEATURES)
    assert abs(np.median(x[:, 0])) < 5 and abs(np.median(x[:, 2])) < 2


def test_gearbox_fault_shows_in_residuals():
    r = residuals(SCEN["gearbox_bearing"]["rows"][0])
    assert r[2] > 8 and r[4] > 2


def test_champion_is_isolation_forest_and_flags_faults(champion):
    det, entry = champion
    assert entry["version"] == "iforest-v1" and det.kind == "isolation_forest"
    assert not score_window(det, SCEN["normal"]["rows"]).anomalous
    for f in ("gearbox_bearing", "pitch_fault", "generator_overheat", "icing"):
        assert score_window(det, SCEN[f]["rows"]).anomalous, f


def test_zscore_fallback_detector_works_without_sklearn():
    det = ZScoreDetector(z_limit=4).fit(matrix(train_rows("normal_train.json")))
    assert score_window(det, SCEN["generator_overheat"]["rows"]).anomalous
    assert not score_window(det, SCEN["normal"]["rows"]).anomalous
    assert make_detector({"kind": "zscore"}).kind == "zscore"


def test_registry_refuses_changed_training_data(tmp_path):
    reg = json.loads(REGISTRY.read_text())
    reg["versions"][0]["training_data_hash"] = "0" * 16
    p = tmp_path / "registry.json"
    p.write_text(json.dumps(reg))
    with pytest.raises(RegistryError):
        DetectorRegistry(p).load_champion()


def test_episode_retrieval_and_diagnosis(champion):
    det, _ = champion
    store = EpisodeStore.seeded(det)
    sig = score_window(det, SCEN["pitch_fault"]["rows"]).signature
    sim = store.similar(sig)
    assert diagnose(sim)[0] == "pitch_fault" and all(s["episode_id"].startswith("EP-") for s in sim)


def test_unknown_pattern_when_nothing_similar():
    assert diagnose([{"episode_id": "x", "diagnosis": "icing", "similarity": 0.2}]) == (
        "unknown_pattern",
        0.0,
    )
    assert CATALOG["unknown_pattern"] == ["schedule_general_inspection"]


def test_episode_write_needs_named_technician(champion):
    store = EpisodeStore.seeded(champion[0])
    with pytest.raises(ValueError):
        store.write({"episode_id": "e", "signature": [0.0] * 7, "confirmed_by": ""})


def test_heldout_scores_for_champion(champion):
    s = evaluate_detector(champion[0])
    assert s["recall"] >= 0.9 and s["fpr"] <= 0.1


def test_promotion_rejects_noisy_candidate_and_logs_it(tmp_path):
    p = tmp_path / "registry.json"
    shutil.copy(REGISTRY, p)
    rec = promote(
        "noisy",
        {"kind": "isolation_forest", "n_estimators": 100, "contamination": 0.2, "random_state": 7},
        "eng",
        p,
    )
    reg = json.loads(p.read_text())
    assert rec["decision"] == "rejected" and reg["champion"] == "iforest-v1"
    assert reg["audit"][-1]["candidate"] == "noisy"


def test_promotion_accepts_good_candidate_with_approver(tmp_path):
    p = tmp_path / "registry.json"
    shutil.copy(REGISTRY, p)
    rec = promote(
        "iforest-v2",
        {"kind": "isolation_forest", "n_estimators": 200, "contamination": 0.03, "random_state": 7},
        "jane (reliability)",
        p,
    )
    assert rec["decision"] == "promoted" and json.loads(p.read_text())["champion"] == "iforest-v2"


def test_promotion_needs_named_approver(tmp_path):
    with pytest.raises(ValueError):
        promote("x", {"kind": "zscore"}, "  ", tmp_path / "r.json")
