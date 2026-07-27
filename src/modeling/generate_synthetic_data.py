"""
Synthetic METSI-EWS data generator.

Simulates a unit-week panel (unit_id stands in for Tshwane wards/zones —
swap this for real boundary IDs once the city/StatsSA data lands).

Design choices, on purpose, so the synthetic data is USEFUL for testing a
real pipeline rather than just random noise:
  - Static unit attributes (infra age, pipe material, informal settlement %,
    population density) are correlated with each other in realistic ways.
  - A small subset of units are flagged as "known hotspots" (standing in for
    Hammanskraal/Temba, Sunnyside/Unisa, Soshanguve, Babelegi, Zithobeni),
    and these units are seeded with older infrastructure and higher NRW —
    so the model has a real, recoverable signal to find via SHAP later.
  - Burst events are simulated sequentially per unit per week, influenced by
    a latent risk score (age, NRW, maintenance recency, rainfall, hotspot
    status), then maintenance reactively resets risk after a burst — this
    creates realistic temporal dependency, not iid noise.
  - The ML *label* is burst_occurred in the FOLLOWING week, built from
    features known only up to the current week — avoiding leakage by design.
"""

from pathlib import Path

import numpy as np
import pandas as pd

RNG = np.random.default_rng(42)

# This script lives in <project_root>/src/, data goes in <project_root>/data/
# Using a path relative to this file (not a hardcoded absolute path) so the
# project works no matter what folder it's extracted/cloned into.
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data" / "model_outputs" / "synthetic"
DATA_DIR.mkdir(parents=True, exist_ok=True)

N_UNITS = 107          # placeholder for Tshwane's 107 wards
N_WEEKS = 156          # 3 years of weekly snapshots
N_HOTSPOTS = 10        # ~9% of units, standing in for known crisis areas
START_DATE = "2024-01-01"

PIPE_MATERIALS = ["asbestos_cement", "cast_iron", "steel", "pvc"]


def _sigmoid(x):
    return 1 / (1 + np.exp(-x))


def _zscore(x):
    return (x - np.mean(x)) / (np.std(x) + 1e-9)


def generate_unit_attributes():
    """Static, per-unit attributes — generated once."""
    unit_id = np.arange(1, N_UNITS + 1)
    is_hotspot = np.zeros(N_UNITS, dtype=int)
    hotspot_idx = RNG.choice(N_UNITS, size=N_HOTSPOTS, replace=False)
    is_hotspot[hotspot_idx] = 1

    # Hotspots skew older infrastructure + denser, more informal settlement
    infra_age_years = np.where(
        is_hotspot == 1,
        RNG.uniform(42, 65, N_UNITS),
        RNG.uniform(5, 42, N_UNITS),
    )
    informal_settlement_pct = np.where(
        is_hotspot == 1,
        RNG.uniform(30, 70, N_UNITS),
        RNG.uniform(0, 35, N_UNITS),
    )
    population_density = np.where(
        is_hotspot == 1,
        RNG.uniform(3000, 9000, N_UNITS),
        RNG.uniform(500, 6000, N_UNITS),
    )

    # Older infra -> more likely to be asbestos cement / cast iron
    pipe_material = []
    for age in infra_age_years:
        if age > 45:
            probs = [0.45, 0.30, 0.15, 0.10]
        elif age > 25:
            probs = [0.20, 0.25, 0.30, 0.25]
        else:
            probs = [0.05, 0.10, 0.30, 0.55]
        pipe_material.append(RNG.choice(PIPE_MATERIALS, p=probs))

    baseline_nrw_pct = np.clip(
        20 + 0.5 * infra_age_years + 8 * is_hotspot + RNG.normal(0, 5, N_UNITS),
        8, 75,
    )

    return pd.DataFrame({
        "unit_id": unit_id,
        "is_known_hotspot": is_hotspot,
        "infra_age_years": infra_age_years.round(1),
        "pipe_material": pipe_material,
        "informal_settlement_pct": informal_settlement_pct.round(1),
        "population_density": population_density.round(0),
        "baseline_nrw_pct": baseline_nrw_pct.round(1),
    })


def generate_rainfall_series(n_weeks):
    """Seasonal South African rainfall pattern (wet Oct-Mar, dry Jun-Aug)."""
    week = np.arange(n_weeks)
    seasonal = 60 + 55 * np.sin(2 * np.pi * (week - 13) / 52)
    seasonal = np.clip(seasonal, 0, None)
    noise = RNG.gamma(2.0, 8.0, n_weeks)
    return np.clip(seasonal * 0.5 + noise, 0, None).round(1)


def simulate_panel(units_df):
    """Sequential per-unit, per-week simulation of NRW, maintenance, and bursts."""
    rainfall_by_week = generate_rainfall_series(N_WEEKS)
    dates = pd.date_range(START_DATE, periods=N_WEEKS, freq="W-MON")

    records = []
    for _, u in units_df.iterrows():
        days_since_maintenance = RNG.integers(0, 180)
        recent_bursts = []  # rolling window of burst flags, trailing 13 weeks
        nrw_now = u["baseline_nrw_pct"]

        for w in range(N_WEEKS):
            rainfall = rainfall_by_week[w]

            # NRW drifts slowly, nudged up by rainfall stress and neglect
            nrw_now = np.clip(
                nrw_now + RNG.normal(0, 1.0) + 0.01 * rainfall
                - 0.02 * (1 if days_since_maintenance < 30 else 0) * 5,
                5, 85,
            )

            historical_incidents_90d = sum(recent_bursts[-13:])

            # Latent risk (standardized-ish, hand-tuned weights)
            z = (
                0.08 * (u["infra_age_years"] - 30)
                + 0.10 * (nrw_now - 35)
                + 0.02 * (days_since_maintenance - 90)
                + 3.5 * u["is_known_hotspot"]
                + 0.025 * (rainfall - 60)
                + 0.5 * historical_incidents_90d
                + RNG.normal(0, 0.25)
            )
            risk_latent = _sigmoid(z * 0.45)  # 0-1, used only to drive simulation

            # Burst probability stays low even for risky units (rare-event realism)
            burst_prob = 0.09 * risk_latent ** 1.3
            burst_occurred = int(RNG.random() < burst_prob)

            records.append({
                "unit_id": u["unit_id"],
                "week_start": dates[w],
                "week_index": w,
                "infra_age_years": u["infra_age_years"],
                "pipe_material": u["pipe_material"],
                "informal_settlement_pct": u["informal_settlement_pct"],
                "population_density": u["population_density"],
                "is_known_hotspot": u["is_known_hotspot"],
                "nrw_pct": round(nrw_now, 2),
                "rainfall_mm": rainfall,
                "days_since_maintenance": days_since_maintenance,
                "historical_incidents_90d": historical_incidents_90d,
                "burst_occurred": burst_occurred,
            })

            recent_bursts.append(burst_occurred)
            if burst_occurred:
                days_since_maintenance = 0
                nrw_now = max(5, nrw_now - RNG.uniform(5, 15))  # repair improves NRW
            else:
                days_since_maintenance += 7
                # small chance of routine/preventive maintenance
                if RNG.random() < 0.01:
                    days_since_maintenance = 0

    return pd.DataFrame.from_records(records)


def add_rolling_features(panel):
    panel = panel.sort_values(["unit_id", "week_index"]).reset_index(drop=True)
    panel["nrw_pct_roll4"] = (
        panel.groupby("unit_id")["nrw_pct"]
        .transform(lambda s: s.rolling(4, min_periods=1).mean())
        .round(2)
    )
    panel["rainfall_roll4"] = (
        panel.groupby("unit_id")["rainfall_mm"]
        .transform(lambda s: s.rolling(4, min_periods=1).mean())
        .round(2)
    )
    return panel


def add_next_week_label(panel):
    """Label = did THIS unit burst in the FOLLOWING week. Drops last week per unit
    (no future week available) to avoid any leakage."""
    panel = panel.sort_values(["unit_id", "week_index"]).reset_index(drop=True)
    panel["burst_next_week"] = panel.groupby("unit_id")["burst_occurred"].shift(-1)
    panel = panel.dropna(subset=["burst_next_week"]).copy()
    panel["burst_next_week"] = panel["burst_next_week"].astype(int)
    return panel


def main():
    units_df = generate_unit_attributes()
    panel = simulate_panel(units_df)
    panel = add_rolling_features(panel)
    panel = add_next_week_label(panel)

    out_path = DATA_DIR / "synthetic_panel.csv"
    panel.to_csv(out_path, index=False)
    units_df.to_csv(DATA_DIR / "units_static.csv", index=False)

    print(f"Generated {len(panel)} unit-week rows across {units_df.shape[0]} units, "
          f"{panel['week_index'].nunique()} weeks.")
    print(f"Overall burst_next_week rate: {panel['burst_next_week'].mean():.4f}")
    print(f"Hotspot units: {units_df['is_known_hotspot'].sum()} / {len(units_df)}")
    hotspot_rate = panel.loc[panel.is_known_hotspot == 1, "burst_next_week"].mean()
    normal_rate = panel.loc[panel.is_known_hotspot == 0, "burst_next_week"].mean()
    print(f"Burst rate — hotspot units: {hotspot_rate:.4f} | other units: {normal_rate:.4f}")
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
