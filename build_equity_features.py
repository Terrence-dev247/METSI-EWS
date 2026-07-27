"""
METSI-EWS  —  build_equity_features.py
========================================
Processes Census 2011 Small Area Layer (SAL) data received from Statistics
South Africa (July 2026) into ward-level equity indicators for the Equity
Check tab.

Inputs
------
data/raw/sal/Census 2011_Tshwane_SAL_Dwellings.xlsx
data/raw/sal/Census 2011_Tshwane_SAL_Piped water.xlsx
data/interim/sal_ward_lookup.csv

Output
------
data/processed/census_sal_equity.csv
    ward_id                 : TSH_N
    informal_settlement_pct : informal dwellings / total dwellings × 100
    no_piped_water_pct      : HH with no piped water access / total HH × 100
    total_dw                : total dwellings in ward (Census 2011)
    total_hh                : total households in ward (Census 2011)
"""

from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent

DW_FILE  = BASE_DIR / "data" / "raw" / "sal" / "Census 2011_Tshwane_SAL_Dwellings.xlsx"
PW_FILE  = BASE_DIR / "data" / "raw" / "sal" / "Census 2011_Tshwane_SAL_Piped water.xlsx"
LOOKUP   = BASE_DIR / "data" / "interim" / "sal_ward_lookup.csv"
OUT_FILE = BASE_DIR / "data" / "processed" / "census_sal_equity.csv"


def _parse_numeric(series):
    return pd.to_numeric(series.replace("-", "0"), errors="coerce").fillna(0)


def build_equity_features():
    # ── Dwellings ─────────────────────────────────────────────────────────────
    dw = pd.read_excel(DW_FILE, sheet_name=0, header=None)
    dw = dw.iloc[7:].reset_index(drop=True)
    dw.columns = ["SAL_CODE", "formal", "traditional", "informal", "other", "total_dw"]
    dw["SAL_CODE"] = pd.to_numeric(dw["SAL_CODE"], errors="coerce")
    dw = dw.dropna(subset=["SAL_CODE"])
    for c in dw.columns[1:]:
        dw[c] = _parse_numeric(dw[c])
    dw["SAL_CODE"] = dw["SAL_CODE"].astype(int)
    print(f"Dwellings: {len(dw)} SALs, {dw['total_dw'].sum():.0f} total dwellings")

    # ── Piped Water ───────────────────────────────────────────────────────────
    pw = pd.read_excel(PW_FILE, sheet_name=0, header=None)
    pw = pw.iloc[7:].reset_index(drop=True)
    pw.columns = [
        "SAL_CODE", "inside_dwell", "inside_yard",
        "comm_lt200", "comm_200_500", "comm_500_1000", "comm_gt1000", "no_access",
    ]
    pw["SAL_CODE"] = pd.to_numeric(pw["SAL_CODE"], errors="coerce")
    pw = pw.dropna(subset=["SAL_CODE"])
    for c in pw.columns[1:]:
        pw[c] = _parse_numeric(pw[c])
    pw["SAL_CODE"] = pw["SAL_CODE"].astype(int)
    pw["total_hh"] = pw[
        ["inside_dwell", "inside_yard", "comm_lt200", "comm_200_500",
         "comm_500_1000", "comm_gt1000", "no_access"]
    ].sum(axis=1)
    print(f"Piped Water: {len(pw)} SALs, {pw['total_hh'].sum():.0f} total households")

    # ── Join to ward lookup ───────────────────────────────────────────────────
    lookup = pd.read_csv(LOOKUP)[["SAL_CODE", "ward_id"]]
    merged = lookup.merge(dw[["SAL_CODE", "informal", "total_dw"]], on="SAL_CODE", how="left")
    merged = merged.merge(pw[["SAL_CODE", "no_access", "total_hh"]], on="SAL_CODE", how="left")

    unmatched = merged["total_dw"].isna().sum()
    if unmatched:
        print(f"Warning: {unmatched} SALs unmatched — check lookup vs. data SAL codes")

    # ── Aggregate to ward ─────────────────────────────────────────────────────
    ward = (
        merged.groupby("ward_id")
        .agg(informal=("informal", "sum"), total_dw=("total_dw", "sum"),
             no_access=("no_access", "sum"), total_hh=("total_hh", "sum"))
        .reset_index()
    )
    ward["informal_settlement_pct"] = (
        ward["informal"] / ward["total_dw"].replace(0, float("nan")) * 100
    ).round(2)
    ward["no_piped_water_pct"] = (
        ward["no_access"] / ward["total_hh"].replace(0, float("nan")) * 100
    ).round(2)

    result = ward[["ward_id", "informal_settlement_pct", "no_piped_water_pct",
                   "total_dw", "total_hh"]]
    result.to_csv(OUT_FILE, index=False)
    print(f"\nSaved: {OUT_FILE}")
    print(f"  Wards: {len(result)}")
    print(f"  Informal %: {result['informal_settlement_pct'].min():.1f}% – "
          f"{result['informal_settlement_pct'].max():.1f}%")
    print(f"  No piped water %: {result['no_piped_water_pct'].min():.1f}% – "
          f"{result['no_piped_water_pct'].max():.1f}%")
    return result


if __name__ == "__main__":
    build_equity_features()
