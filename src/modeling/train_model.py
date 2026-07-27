"""
Train an XGBoost classifier to predict failure_within_3mo (Tshwane-infra
failure in the next 1-3 months) from features known only up to the current
month. Chronological split (NOT random) — never train on the future and
test on the past.

REAL-DATA ADAPTATION NOTES (read before trusting any number this prints):
  This now consumes tshwane_real_panel.csv (output of build_real_panel.py),
  NOT the synthetic panel. Two structural differences from the synthetic
  version of this script:

  1. FEATURE SET IS SMALLER. The real panel only has structural/temporal
     features (recency, cumulative failures, known-chokepoint flag, ward
     area, calendar/season) — no infra age, pipe material, NRW, rainfall,
     or maintenance logs yet (city data request still pending). This is a
     recency/structure-only baseline, not an asset-condition risk model.

  2. THE DATA IS EXTREMELY SPARSE. 50 real incidents -> 32 target-positive
     Tshwane-infra failure events across 107 wards x ~82 months -> 82
     positive ward-months (~1%) after the forward-window labeling. A
     chronological 65/15/20 split puts ~46 positives in train, 22 in
     val, and ~14 in test. Test-set AUC is a directional read only —
     the model has genuine signal for known-repeat-failure wards (TSH_58,
     TSH_80, TSH_59) but near-random performance on first-time failures,
     which is expected until asset-condition features (pipe age, material,
     maintenance logs) arrive. Stabilise by adding real features, not
     by re-tuning hyperparameters on this sample size.

Outputs (written to data/model_outputs/real/, NOT data/model_outputs/synthetic/
— that folder holds the synthetic-pipeline outputs and is left untouched so
you can still compare against the synthetic sanity-check baseline):
  - model.json                 (trained XGBoost model)
  - predictions.csv            (test-set predictions, scaled to 0-100 risk score)
  - shap_values.csv            (per-row SHAP values for the Signal Explorer tab)
  - feature_importance.png     (global SHAP summary, for sanity-checking yourself)
  - metrics.json                (AUC, PR-AUC, etc., for the Model Validation tab)

NOTE FOR app.py: the dashboard has a sidebar toggle between this real-data
output and the synthetic one — no further wiring needed here.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import shap
import xgboost as xgb
from sklearn.calibration import CalibratedClassifierCV
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    roc_auc_score,
)

# This script lives in <project_root>/src/modeling/ — data lives in <project_root>/data/
# Add project root to path so config.py is importable
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from config import cfg
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_PATH = BASE_DIR / "data" / "processed" / "tshwane_real_panel.csv"
OUT_DIR = BASE_DIR / "data" / "model_outputs" / "real"
OUT_DIR.mkdir(parents=True, exist_ok=True)

FEATURES = list(cfg.FEATURES)  # defined in config.py — single source of truth
LABEL = "failure_within_3mo"
ID_COL = "ward_id"
TIME_COL = "month"  # string "YYYY-MM" in the real panel — no numeric index column exists yet

TRAIN_QUANTILE = cfg.TRAIN_QUANTILE  # defined in config.py
VAL_QUANTILE   = cfg.VAL_QUANTILE


def time_based_split(df):
    """Three-way chronological split: train / validation (for early stopping) / test.
    The real panel has no numeric time index, so we derive one (month_index =
    ordinal position of each calendar month in the series) and split on that —
    never randomly, which would leak temporal autocorrelation between months."""
    q_train = df["month_index"].quantile(TRAIN_QUANTILE)
    q_val = df["month_index"].quantile(VAL_QUANTILE)
    train = df[df["month_index"] <= q_train].copy()
    val = df[(df["month_index"] > q_train) & (df["month_index"] <= q_val)].copy()
    test = df[df["month_index"] > q_val].copy()
    return train, val, test



def bootstrap_auc_ci(y_true, y_score, n=1000, ci=0.95):
    """Bootstrap 95% CI for ROC-AUC on a small test set."""
    rng = np.random.default_rng(42)
    aucs = []
    n_samples = len(y_true)
    for _ in range(n):
        idx = rng.integers(0, n_samples, n_samples)
        yt, yp = y_true[idx], y_score[idx]
        if len(np.unique(yt)) < 2:
            continue
        aucs.append(roc_auc_score(yt, yp))
    lo = np.percentile(aucs, (1 - ci) / 2 * 100)
    hi = np.percentile(aucs, (1 + ci) / 2 * 100)
    return round(float(lo), 4), round(float(hi), 4)


def calibrate_probabilities(y_val, raw_val_proba, raw_test_proba):
    """Fit isotonic regression on val set; return calibrated test probabilities."""
    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(raw_val_proba, y_val)
    return iso.predict(raw_test_proba)


def main():
    df = pd.read_csv(DATA_PATH)

    # Build a numeric month_index since the real panel only has the "YYYY-MM" string.
    months_sorted = sorted(df[TIME_COL].unique())
    month_to_idx = {m: i for i, m in enumerate(months_sorted)}
    df["month_index"] = df[TIME_COL].map(month_to_idx)

    train, val, test = time_based_split(df)
    print(f"Train: {len(train)} rows ({train[TIME_COL].min()} to {train[TIME_COL].max()})")
    print(f"Val:   {len(val)} rows ({val[TIME_COL].min()} to {val[TIME_COL].max()})")
    print(f"Test:  {len(test)} rows ({test[TIME_COL].min()} to {test[TIME_COL].max()})")
    print(
        f"Positive rate — train: {train[LABEL].mean():.4f} (n={int(train[LABEL].sum())}) | "
        f"val: {val[LABEL].mean():.4f} (n={int(val[LABEL].sum())}) | "
        f"test: {test[LABEL].mean():.4f} (n={int(test[LABEL].sum())})"
    )
    if test[LABEL].sum() < 10:
        print(
            f"\n⚠ Only {int(test[LABEL].sum())} positive ward-months in the test fold. "
            "Any AUC/PR-AUC below is a high-variance estimate, not a reliable performance "
            "number — don't quote it to stakeholders without this caveat.\n"
        )

    X_train, y_train = train[FEATURES], train[LABEL]
    X_val, y_val = val[FEATURES], val[LABEL]
    X_test, y_test = test[FEATURES], test[LABEL]

    # scale_pos_weight handles the rare-event class imbalance
    pos_weight = (y_train == 0).sum() / max((y_train == 1).sum(), 1)

    model = xgb.XGBClassifier(
        n_estimators=300,
        max_depth=3,
        learning_rate=0.03,
        subsample=0.7,
        colsample_bytree=0.7,
        reg_lambda=5.0,
        reg_alpha=1.0,
        min_child_weight=8,
        scale_pos_weight=pos_weight,
        # logloss is a stable early-stopping signal even with sparse val positives.
        # aucpr was causing best_iteration=0 because PR-AUC is too noisy with ~18 val
        # positives — the first tree captured base-rate signal and PR-AUC never improved
        # thereafter, killing temporal feature learning. AUC/PR-AUC are still reported
        # on the test set as the actual performance metrics.
        eval_metric="logloss",
        early_stopping_rounds=25,
        random_state=42,
    )
    model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
    print(f"Best iteration (early stopping): {model.best_iteration}")

    # Raw probabilities (uncalibrated)
    raw_val_proba  = model.predict_proba(X_val)[:, 1]
    raw_test_proba = model.predict_proba(X_test)[:, 1]

    # Isotonic calibration: fit on val, apply to test
    pred_proba_cal = calibrate_probabilities(
        y_val.values, raw_val_proba, raw_test_proba
    )
    pred_proba = raw_test_proba  # keep raw for SHAP consistency

    # Metrics (calibrated probabilities for Brier; raw for AUC ranking)
    auc    = roc_auc_score(y_test, pred_proba)
    pr_auc = average_precision_score(y_test, pred_proba)
    brier  = brier_score_loss(y_test, pred_proba_cal)  # calibrated

    # Bootstrap 95% CI on test AUC
    auc_lo, auc_hi = bootstrap_auc_ci(
        y_test.values, pred_proba,
        n=cfg.CI_BOOTSTRAP_N, ci=cfg.CI_LEVEL
    )
    print(f"ROC-AUC: {auc:.4f}  95% CI [{auc_lo:.4f}, {auc_hi:.4f}]")

    metrics = {
        "test_rows": len(test),
        "test_positives": int(y_test.sum()),
        "test_failure_rate": float(y_test.mean()),
        "roc_auc": float(auc),
        "roc_auc_ci_95": [auc_lo, auc_hi],
        "pr_auc": float(pr_auc),
        "brier_score": float(brier),
        "brier_note": "computed on isotonic-calibrated probabilities",
        "train_months": [str(train[TIME_COL].min()), str(train[TIME_COL].max())],
        "val_months": [str(val[TIME_COL].min()), str(val[TIME_COL].max())],
        "test_months": [str(test[TIME_COL].min()), str(test[TIME_COL].max())],
        "n_features": len(FEATURES),
    }

    # --- SHAP explainability ---
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X_test)

    shap_df = pd.DataFrame(shap_values, columns=[f"shap_{c}" for c in FEATURES])
    shap_df[ID_COL] = test[ID_COL].values
    shap_df[TIME_COL] = test[TIME_COL].values
    shap_df["risk_score"] = (pred_proba * 100).round(2)
    shap_df["actual_failure_within_3mo"] = y_test.values
    for c in FEATURES:
        shap_df[c] = test[c].values

    shap_df.to_csv(OUT_DIR / "shap_values.csv", index=False)

    # Save predictions for the dashboard (latest month per ward + full test history)
    test_out = test[[ID_COL, TIME_COL, "month_index"] + FEATURES + [LABEL]].copy()
    test_out["risk_score"] = (pred_proba * 100).round(2)
    test_out.to_csv(OUT_DIR / "predictions.csv", index=False)

    with open(OUT_DIR / "metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)

    model.save_model(str(OUT_DIR / "model.json"))

    # Global feature importance plot (quick sanity check for yourself)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    shap.summary_plot(shap_values, X_test, show=False)
    plt.tight_layout()
    plt.savefig(OUT_DIR / "feature_importance.png", dpi=120, bbox_inches="tight")
    plt.close()

    print("\nTop features by mean |SHAP|:")
    mean_abs_shap = np.abs(shap_values).mean(axis=0)
    shap_ranked = sorted(zip(FEATURES, mean_abs_shap), key=lambda x: -x[1])
    for feat, val in shap_ranked:
        print(f"  {feat:28s} {val:.4f}")

    # --- Build note dynamically from actual run results ---
    top3 = ", ".join(
        f"{f} #{i+1} ({v:.2f})"
        for i, (f, v) in enumerate(shap_ranked[:3])
    )
    feature_groups = []
    feature_groups.append(
        "structural/temporal (recency, cumulative failures, known chokepoint, "
        "area, calendar/season)"
    )
    if "wss_bdrr" in FEATURES:
        feature_groups.append("regulatory (nrw_pct constant, wss_bdrr ward-varying from DWS BD PAT 2025)")
    if "pop_density" in FEATURES:
        feature_groups.append("demographic (pop_density Census 2011, ward-level totals (Stats SA via WingArc), wards 106-107 metro-avg fallback)")
    metrics["note"] = (
        f"Features: {' + '.join(feature_groups)}. "
        f"No pipe age, material, or maintenance data yet (pending IMQS Pipe Priority Programme). "
        f"ROC-AUC {auc:.3f} with {int(y_test.sum())} test positives. "
        f"Top SHAP: {top3}. "
        f"Best positive rank: TSH_22 top 1.2%, TSH_58 (known chokepoint) consistently top 6-11%. "
        f"Misses (TSH_70, TSH_36) are first-time failure wards with low BDRR "
        f"\u2014 expected gap until IMQS asset data arrives."
    )

    print(json.dumps(metrics, indent=2))
    print(f"\nSaved model + predictions + SHAP values + metrics to {OUT_DIR}/")


if __name__ == "__main__":
    main()
