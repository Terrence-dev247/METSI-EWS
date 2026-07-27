"""
tests/test_pipeline.py
Tests for panel structure and feature engineering outputs.
Skipped automatically if data files are not present (CI-safe).
"""
import sys
import pytest
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from config import cfg

PANEL_PATH = ROOT / cfg.PANEL_FILE


@pytest.fixture(scope="module")
def panel():
    if not PANEL_PATH.exists():
        pytest.skip(f"Panel not found at {PANEL_PATH} — run build_real_panel.py first")
    return pd.read_csv(PANEL_PATH)


def test_panel_ward_count(panel):
    assert panel["ward_id"].nunique() == cfg.N_WARDS, (
        f"Expected {cfg.N_WARDS} wards, got {panel['ward_id'].nunique()}"
    )

def test_panel_no_duplicate_ward_months(panel):
    dups = panel.duplicated(subset=["ward_id", "month"]).sum()
    assert dups == 0, f"{dups} duplicate ward×month rows found"

def test_panel_required_columns(panel):
    # Core columns always required
    core = {"ward_id", "month", cfg.LABEL_COL}
    missing_core = core - set(panel.columns)
    assert not missing_core, f"Missing core columns: {missing_core}"
    # Feature columns — warn if absent (may need pipeline re-run)
    missing_features = set(cfg.FEATURES) - set(panel.columns)
    if missing_features:
        pytest.skip(f"Features not yet in panel: {missing_features} — re-run run_pipeline.py")

def test_panel_positive_rate_plausible(panel):
    rate = panel[cfg.LABEL_COL].mean()
    assert 0.001 < rate < 0.10, f"Positive rate {rate:.3%} outside expected range"

def test_panel_no_negative_area(panel):
    assert (panel["area_km2"] >= 0).all(), "Negative area_km2 values found"

def test_panel_pop_density_positive(panel):
    if "pop_density" in panel.columns:
        assert (panel["pop_density"] >= 0).all(), "Negative pop_density found"

def test_panel_month_format(panel):
    import re
    sample = panel["month"].dropna().iloc[0]
    assert re.match(r"^\d{4}-\d{2}$", str(sample)), f"Unexpected month format: {sample}"
