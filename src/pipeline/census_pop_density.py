#!/usr/bin/env python3
"""
census_pop_density.py
────────────────────────────────────────────────────────────────────────────
Compute pop_density (persons / km²) for all 107 City of Tshwane wards and
merge the feature into the real panel (tshwane_real_panel.csv).

Data source:
    Statistics South Africa — Census 2011, WingArc/SuperCROSS release v1.3
    File: data/interim/census_2011_ward_population.csv
    All 107 wards; wards 106 & 107 use Tshwane metro-average fallback (27,824)
    because they are absent from the Stats SA release.

    Reference: Census 2011 Tshwane total = 2,921,486 persons (105 wards).
    WorldPop 2020 raster gives 3.82M (+30.8%) — expected population growth
    over 9 years; documented limitation, not an error.

Pipeline position:
    Run AFTER build_real_panel.py, BEFORE train_model.py.
    Overwrites data/processed/tshwane_real_panel.csv in place.

Run:
    python src/pipeline/census_pop_density.py

Inputs:
    data/raw/tshwane_wards_2020.geojson
    data/interim/census_2011_ward_population.csv
    data/processed/tshwane_real_panel.csv

Outputs:
    data/interim/ward_pop_density.csv           ward-level reference
    data/processed/tshwane_real_panel.csv       panel + pop_density (overwrite)
"""

import sys
import pandas as pd
import geopandas as gpd
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR      = PROJECT_ROOT / "data" / "raw"
INTERIM_DIR  = PROJECT_ROOT / "data" / "interim"
PROCESSED_DIR= PROJECT_ROOT / "data" / "processed"

WARD_GEO  = RAW_DIR       / "tshwane_wards_2020.geojson"
CENSUS_CSV= INTERIM_DIR   / "census_2011_ward_population.csv"
PANEL_PATH= PROCESSED_DIR / "tshwane_real_panel.csv"
WARD_OUT  = INTERIM_DIR   / "ward_pop_density.csv"


def load_census_pop() -> pd.DataFrame:
    if not CENSUS_CSV.exists():
        print(f"✗  Census file not found: {CENSUS_CSV}")
        sys.exit(1)
    df = pd.read_csv(CENSUS_CSV, dtype={"ward_code": str})
    n_fallback = (df["source"] == "metro_avg_fallback").sum()
    print(f"[census]  Loaded {len(df)} wards — "
          f"{len(df) - n_fallback} Census 2011, {n_fallback} metro-avg fallback")
    return df


def load_ward_areas() -> pd.DataFrame:
    gdf = gpd.read_file(WARD_GEO)
    gdf.geometry = gdf.buffer(0)
    gdf_utm = gdf.to_crs(epsg=32735)
    gdf["area_km2"] = gdf_utm.geometry.area / 1e6
    gdf["ward_id"]  = gdf["WardLabel"]
    return gdf[["ward_id", "area_km2"]].drop_duplicates(subset="ward_id")


def compute_pop_density() -> pd.DataFrame:
    census = load_census_pop()
    areas  = load_ward_areas()
    ward_df = areas.merge(census[["ward_id","pop_total","source"]], on="ward_id", how="left")

    n_missing = ward_df["pop_total"].isna().sum()
    if n_missing:
        raise ValueError(f"Census population missing for: "
                         f"{ward_df[ward_df['pop_total'].isna()]['ward_id'].tolist()}")

    ward_df["pop_census_2011"]     = ward_df["pop_total"].astype(int)
    ward_df["pop_density"]         = ward_df["pop_census_2011"] / ward_df["area_km2"]
    ward_df["pop_density_imputed"] = ward_df["source"] == "metro_avg_fallback"
    ward_df = ward_df.rename(columns={"ward_id": "WardLabel"})
    return ward_df[["WardLabel","area_km2","pop_census_2011","pop_density","pop_density_imputed"]]


def main() -> None:
    print("=" * 62)
    print("  census_pop_density.py — Census 2011 → pop_density feature")
    print("=" * 62 + "\n")

    ward_df = compute_pop_density()

    print("\n── pop_density (persons/km²) ─────────────────────")
    print(ward_df["pop_density"].describe().round(1).to_string())

    total    = ward_df["pop_census_2011"].sum()
    expected = 2_921_486
    n_fb     = ward_df["pop_density_imputed"].sum()
    print(f"\n[check]  Census pop sum (incl {n_fb} fallbacks): {total:>10,}")
    print(f"         Census 2011 reference (105 wards)    : {expected:>10,}")

    fallbacks = ward_df[ward_df["pop_density_imputed"]]["WardLabel"].tolist()
    if fallbacks:
        print(f"[warn]   Metro-average fallback wards: {fallbacks}")

    low_density = ward_df[ward_df["pop_density"] < 200]["WardLabel"].tolist()
    if low_density:
        print(f"[info]   Low pop_density (<200 p/km²): {low_density} "
              f"— expected for large rural/peri-urban wards in northern Tshwane")
    print("[info]   TSH_38 M:F ratio anomaly (6908:2454) — "
          "likely correctional/military institution; pop_total retained as recorded")

    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    ward_df.to_csv(WARD_OUT, index=False)
    print(f"\n[saved]  {WARD_OUT.relative_to(PROJECT_ROOT)}")

    panel = pd.read_csv(PANEL_PATH)
    panel = panel.drop(columns=["pop_density","pop_density_imputed","pop_worldpop"], errors="ignore")
    panel = panel.merge(
        ward_df[["WardLabel","pop_density","pop_density_imputed"]].rename(columns={"WardLabel":"ward_id"}),
        on="ward_id", how="left"
    )
    null_count = panel["pop_density"].isna().sum()
    panel.to_csv(PANEL_PATH, index=False)
    print(f"[saved]  {PANEL_PATH.relative_to(PROJECT_ROOT)}  "
          f"shape={panel.shape}  pop_density nulls={null_count}")

    print("\n── Done. Run train_model.py to retrain with updated pop_density. ──")


if __name__ == "__main__":
    main()
