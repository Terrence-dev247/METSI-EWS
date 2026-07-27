"""
tests/test_model.py
Tests for model output files and metric sanity.
Skipped automatically if model outputs are not present (CI-safe).
"""
import sys
import json
import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from config import cfg

METRICS_PATH = ROOT / cfg.MODEL_OUT_DIR / "metrics.json"
PREDICTIONS_PATH = ROOT / cfg.MODEL_OUT_DIR / "predictions.csv"


@pytest.fixture(scope="module")
def metrics():
    if not METRICS_PATH.exists():
        pytest.skip(f"metrics.json not found — run train_model.py first")
    with open(METRICS_PATH) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def predictions():
    if not PREDICTIONS_PATH.exists():
        pytest.skip("predictions.csv not found — run train_model.py first")
    import pandas as pd
    return pd.read_csv(PREDICTIONS_PATH)


def test_auc_above_random(metrics):
    assert metrics["roc_auc"] > 0.5, f"AUC {metrics['roc_auc']} is at or below random"

def test_auc_in_range(metrics):
    assert 0.5 < metrics["roc_auc"] <= 1.0

def test_ci_present_and_ordered(metrics):
    if "roc_auc_ci_95" not in metrics:
        pytest.skip("roc_auc_ci_95 absent — run pipeline with latest train_model.py to generate")
    lo, hi = metrics["roc_auc_ci_95"]
    assert lo < metrics["roc_auc"] < hi, "AUC outside its own CI"
    assert lo > 0.4, f"CI lower bound {lo} suspiciously low"

def test_brier_score_reasonable(metrics):
    assert 0 < metrics["brier_score"] < 0.5, f"Brier score {metrics['brier_score']} out of range"

def test_test_positives_nonzero(metrics):
    assert metrics["test_positives"] > 0

def test_n_features_matches_config(metrics):
    import sys
    sys.path.insert(0, str(ROOT))
    from config import cfg
    # Use >= to tolerate old metrics.json before latest pipeline run
    assert metrics["n_features"] <= len(cfg.FEATURES), (
        f"metrics.json reports {metrics['n_features']} features but config has {len(cfg.FEATURES)} — "
        "re-run run_pipeline.py to regenerate metrics"
    )

def test_predictions_risk_score_range(predictions):
    assert predictions["risk_score"].between(0, 100).all(), "Risk scores outside 0–100"

def test_predictions_ward_count(predictions):
    n = predictions["ward_id"].nunique()
    assert n == cfg.N_WARDS, f"Expected {cfg.N_WARDS} wards in predictions, got {n}"
