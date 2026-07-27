"""
Train an XGBoost classifier to predict burst_next_week from features known
only up to the current week. Time-based split (NOT random) so we never train
on the future and test on the past — random splits would leak temporal
autocorrelation between weeks and overstate performance.

Outputs:
  - model.json                 (trained XGBoost model)
  - predictions.csv            (test-set predictions, scaled to 0-100 risk score)
  - shap_values.csv            (per-row SHAP values for the Signal Explorer tab)
  - feature_importance.png     (global SHAP summary, for sanity-checking yourself)
  - metrics.json                (AUC, PR-AUC, etc., for the Model Validation tab)
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import shap
import xgboost as xgb
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    roc_auc_score,
)

# This script lives in <project_root>/src/modeling/, data lives in <project_root>/data/
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data" / "model_outputs" / "synthetic"
DATA_PATH = DATA_DIR / "synthetic_panel.csv"
OUT_DIR = DATA_DIR

FEATURES = [
    "infra_age_years",
    "informal_settlement_pct",
    "population_density",
    "nrw_pct",
    "nrw_pct_roll4",
    "rainfall_mm",
    "rainfall_roll4",
    "days_since_maintenance",
    "historical_incidents_90d",
    "is_known_hotspot",
]
LABEL = "burst_next_week"
TRAIN_FRACTION = 0.8  # chronological — first 80% of weeks train, last 20% test


def time_based_split(df):
    """Three-way chronological split: train / validation (for early stopping) / test.
    Never random — random splits on weekly panel data leak temporal autocorrelation."""
    q_train = df["week_index"].quantile(0.65)
    q_val = df["week_index"].quantile(0.80)
    train = df[df["week_index"] <= q_train].copy()
    val = df[(df["week_index"] > q_train) & (df["week_index"] <= q_val)].copy()
    test = df[df["week_index"] > q_val].copy()
    return train, val, test


def main():
    df = pd.read_csv(DATA_PATH)
    train, val, test = time_based_split(df)
    print(f"Train: {len(train)} rows (weeks 0-{train.week_index.max()})")
    print(f"Val:   {len(val)} rows (weeks {val.week_index.min()}-{val.week_index.max()})")
    print(f"Test:  {len(test)} rows (weeks {test.week_index.min()}-{test.week_index.max()})")
    print(f"Burst rates — train: {train[LABEL].mean():.4f} | val: {val[LABEL].mean():.4f} "
          f"| test: {test[LABEL].mean():.4f}")

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
        eval_metric="aucpr",
        early_stopping_rounds=25,
        random_state=42,
    )
    model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
    print(f"Best iteration (early stopping): {model.best_iteration}")

    pred_proba = model.predict_proba(X_test)[:, 1]
    auc = roc_auc_score(y_test, pred_proba)
    pr_auc = average_precision_score(y_test, pred_proba)
    brier = brier_score_loss(y_test, pred_proba)

    metrics = {
        "test_rows": len(test),
        "test_burst_rate": float(y_test.mean()),
        "roc_auc": float(auc),
        "pr_auc": float(pr_auc),
        "brier_score": float(brier),
        "train_weeks": [int(train.week_index.min()), int(train.week_index.max())],
        "test_weeks": [int(test.week_index.min()), int(test.week_index.max())],
    }
    print(json.dumps(metrics, indent=2))

    # --- SHAP explainability ---
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X_test)

    shap_df = pd.DataFrame(shap_values, columns=[f"shap_{c}" for c in FEATURES])
    shap_df["unit_id"] = test["unit_id"].values
    shap_df["week_start"] = test["week_start"].values
    shap_df["risk_score"] = (pred_proba * 100).round(2)
    shap_df["actual_burst_next_week"] = y_test.values
    for c in FEATURES:
        shap_df[c] = test[c].values

    shap_df.to_csv(OUT_DIR / "shap_values.csv", index=False)

    # Save predictions for the dashboard (latest week per unit + full test history)
    test_out = test[["unit_id", "week_start", "week_index"] + FEATURES + [LABEL]].copy()
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

    print("\nTop features by mean |SHAP|:")
    mean_abs_shap = np.abs(shap_values).mean(axis=0)
    for feat, val in sorted(zip(FEATURES, mean_abs_shap), key=lambda x: -x[1]):
        print(f"  {feat:28s} {val:.4f}")

    print(f"\nSaved model + predictions + SHAP values + metrics to {OUT_DIR}/")


if __name__ == "__main__":
    main()
