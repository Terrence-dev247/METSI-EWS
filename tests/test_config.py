"""
tests/test_config.py
Unit tests for config.py — fast, no I/O, no external data required.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import cfg


def test_ward_count():
    assert cfg.N_WARDS == 107

def test_forecast_window():
    assert cfg.FORECAST_WINDOW == 3

def test_split_quantiles_ordered():
    assert 0 < cfg.TRAIN_QUANTILE < cfg.VAL_QUANTILE < 1

def test_features_non_empty():
    assert len(cfg.FEATURES) >= 10

def test_required_features_present():
    required = {"area_km2", "wss_bdrr", "pop_density", "is_known_chokepoint"}
    assert required.issubset(set(cfg.FEATURES))

def test_xgb_hyperparams_sane():
    assert 0 < cfg.XGB_LEARNING_RATE < 1
    assert 0 < cfg.XGB_SUBSAMPLE <= 1
    assert cfg.XGB_MAX_DEPTH >= 1
    assert cfg.XGB_N_ESTIMATORS >= 100

def test_ci_bootstrap_n():
    assert cfg.CI_BOOTSTRAP_N >= 100

def test_ci_level():
    assert 0.9 <= cfg.CI_LEVEL < 1.0

def test_calibration_method_valid():
    assert cfg.CALIBRATION_METHOD in ("isotonic", "sigmoid")

def test_max_null_rate():
    assert 0 < cfg.MAX_NULL_RATE < 0.5
