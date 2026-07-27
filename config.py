"""
config.py
────────────────────────────────────────────────────────────────────────────
Single source of truth for all tunable constants in the Water Crisis
Intelligence Dashboard pipeline.

Import in any script with:
    from config import cfg

Then reference values as cfg.FORECAST_WINDOW, cfg.TRAIN_QUANTILE, etc.
"""

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class Config:

    # ── Geography ─────────────────────────────────────────────────────────────
    N_WARDS: int = 107                  # City of Tshwane MDB 2020 ward count
    MUNICIPALITY_CODE: str = "799"      # Stats SA / Wazimap code for Tshwane

    # ── Forecast window ───────────────────────────────────────────────────────
    FORECAST_WINDOW: int = 3            # months ahead the model predicts

    # ── Temporal split (applied to month_index quantiles) ────────────────────
    TRAIN_QUANTILE: float = 0.65        # everything ≤ this quantile → train
    VAL_QUANTILE: float = 0.80          # train < x ≤ this → validation

    # ── XGBoost hyperparameters ───────────────────────────────────────────────
    XGB_N_ESTIMATORS: int = 300
    XGB_MAX_DEPTH: int = 3
    XGB_LEARNING_RATE: float = 0.03
    XGB_SUBSAMPLE: float = 0.7
    XGB_COLSAMPLE: float = 0.7
    XGB_EARLY_STOPPING: int = 25

    # ── Feature list ──────────────────────────────────────────────────────────
    FEATURES: List[str] = field(default_factory=lambda: [
        "area_km2",
        "failure_count_this_month",
        "failure_occurred_this_month",
        "cumulative_failures_to_date",
        "months_since_last_failure",
        "is_known_chokepoint",
        "calendar_month",
        "is_dry_season",
        "nrw_pct",
        "wss_bdrr",
        "pop_density",
    ])

    # ── Column names ──────────────────────────────────────────────────────────
    LABEL_COL: str = "failure_within_3mo"
    ID_COL: str = "ward_id"
    TIME_COL: str = "month"

    # ── Data validation guards ────────────────────────────────────────────────
    MIN_WARD_COUNT: int = 107           # hard fail if panel has fewer wards
    MIN_POSITIVES: int = 50             # hard fail if too few target=1 rows
    MAX_NULL_RATE: float = 0.05         # hard fail if any feature > 5% null

    # ── Confidence interval ───────────────────────────────────────────────────
    CI_BOOTSTRAP_N: int = 1000          # bootstrap resamples for AUC CI
    CI_LEVEL: float = 0.95              # confidence level (95%)

    # ── Calibration ───────────────────────────────────────────────────────────
    CALIBRATION_METHOD: str = "isotonic"  # "isotonic" or "sigmoid" (Platt)

    # ── Paths (relative to project root) ─────────────────────────────────────
    PANEL_FILE: str = "data/processed/tshwane_real_panel.csv"
    MODEL_OUT_DIR: str = "data/model_outputs/real"
    WARDS_GEOJSON: str = "data/raw/tshwane_wards_2020.geojson"
    INCIDENTS_FILE: str = "data/processed/tshwane_water_incidents_labeled.csv"
    CENSUS_2011_PATH: str = "data/interim/census_2011_ward_population.csv"


cfg = Config()
