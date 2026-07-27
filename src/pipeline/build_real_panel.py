"""
build_real_panel.py

Builds a ward x month panel for early-warning model training from labeled
real incident data (output of define_target.py) and the Tshwane ward
boundary file.

FEATURE LIMITATION — read before training on this:
  This panel contains structural/temporal features from incident history and
  ward geometry (recency, cumulative failure count, known-chokepoint flag,
  ward area, calendar/season) plus two regulatory-source features:
    nrw_pct=33.0   — Non-Revenue Water %, City of Tshwane 2021/22 (Blue Drop
                     2023). Municipal-level constant: zero intra-panel variance,
                     XGBoost won't split on it. Placeholder for ward/time-varying
                     NRW data.
    wss_bdrr       — Blue Drop Risk Rating (BDRR) of the water supply system
                     serving each ward. Ward-varying (range 24–74%). 14 wards
                     confirmed via geocoding; remainder via nearest-WTW distance.
                     Source: DWS BD PAT Report 2025 (Gauteng). Proxy for
                     management-culture risk; not a direct pipe-failure metric.

  It does NOT yet contain pipe age, pipe material, or maintenance history —
  those requests to datahub@tshwane.gov.za (specifically the IMQS Pipe
  Priority Program export) are still pending. Any model trained on this panel
  is a recency/management-proxy baseline, not a true asset-condition risk model,
  until that data arrives.

Target definition (early-warning framing):
  failure_within_3mo[ward, month_t] = 1 if a Tshwane-infra failure
  (infra_failure_tshwane == 1) occurs in that ward in month t+1, t+2, OR t+3.
  Ward-months where the full forward window isn't observable yet (the last
  3 months of the series, per ward) are DROPPED rather than imputed as
  negative — imputing them as 0 would be a right-censoring leak, not a
  true negative.

Run:
    python build_real_panel.py

Inputs:
    data/processed/tshwane_water_incidents_labeled.csv  (output of define_target.py)
    data/raw/tshwane_wards_2020.geojson
Output:
    data/processed/tshwane_real_panel.csv
"""

import sys
from pathlib import Path

# Config
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
try:
    from config import cfg as _cfg
except ImportError:
    _cfg = None

import numpy as np
import pandas as pd
import geopandas as gpd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

LABELED_INCIDENTS_FILE = PROCESSED_DIR / "tshwane_water_incidents_labeled.csv"
WARDS_GEOJSON_FILE = RAW_DIR / "tshwane_wards_2020.geojson"
OUTPUT_FILE = PROCESSED_DIR / "tshwane_real_panel.csv"

LEAD_WINDOW_MONTHS = 3          # how many months ahead the model predicts — adjust if needed

# Water Supply System BDRR (Blue Drop Risk Rating) per ward.
# Source: DWS Blue Drop Progress Assessment Tool (PAT) Report 2025 (Gauteng), Table 6-14.
# BDRR is a water-quality-management risk score (0%=low risk, 100%=critical) — NOT a direct
# pipe-failure metric, but correlated with overall infrastructure management quality.
# A high BDRR → poor compliance + maintenance culture → likely also worse pipe upkeep.
#
# 14 wards confirmed via geocoding (service-area suburb → sjoin → ward). All others assigned
# via nearest-WTW Euclidean distance (lat/lon), which is an approximation — replace with
# confirmed service-area maps once available from datahub@tshwane.gov.za.
#
# Key confirmed assignments (high signal):
#   TSH_102, TSH_103, TSH_105 → Bronkhorstpruit Town WTW  74.0%  HIGH RISK
#   TSH_49                    → Pretoria Temba WTW         73.3%  HIGH RISK
#   TSH_100                   → Onverwacht borehole        53.6%  MEDIUM
#   TSH_75                    → Klipdrift WTW (Magalies)   39.5%  LOW-MED
#   TSH_5, TSH_50             → Roodeplaat WTW (P. North)  38.1%  LOW-MED
#   TSH_58                    → Pretoria Findlay (Fountains)34.6% LOW
#   TSH_56, TSH_60, TSH_1, TSH_41 → Pretoria Central & South 31.9% LOW
#   TSH_96                    → Walmansthal WTW (Magalies)  27.5% LOW
WSS_BDRR_LOOKUP = {
    # HIGH RISK — Bronkhorstpruit Town WTW (2024 BDRR 74.0%)
    "TSH_102": 74.0, "TSH_103": 74.0, "TSH_105": 74.0,
    # HIGH RISK — Pretoria Temba WTW (2024 BDRR 73.3%)
    "TSH_49": 73.3,
    # MEDIUM — Onverwacht borehole (2024 BDRR 53.6%)
    "TSH_100": 53.6,
    # MEDIUM — Bronkhorstbaai WTW (2024 BDRR 41.5%) — same ward as Bronkhorstpruit,
    # which takes precedence (worst score) since TSH_105 is already assigned 74.0%
    # MEDIUM/LOW — Klipdrift WTW, Magalies Water (2024 BDRR 39.5%)
    "TSH_75": 39.5,
    # LOW-MED — Pretoria North, Roodeplaat WTW (2024 BDRR 38.1%)
    "TSH_5": 38.1, "TSH_50": 38.1,
    # LOW — Pretoria Findlay (Fountains springs, 2024 BDRR 34.6%)
    "TSH_58": 34.6,
    # LOW — Pretoria Central & South (Rietvlei WTW + Rand Water blend, 2024 BDRR 31.9%)
    "TSH_56": 31.9, "TSH_60": 31.9, "TSH_1": 31.9, "TSH_41": 31.9,
    # LOW — Walmansthal, Magalies Water (2024 BDRR 27.5%)
    "TSH_96": 27.5,
    # LOW — Cullinan, Magalies Water (2024 BDRR 24.5%)
    # TSH_100 already assigned Onverwacht (53.6%) — worse score takes precedence
    # LOW — Summerplace WTW (2024 BDRR 24.0%) — small estate, no incident-bearing wards mapped
}
# WTW locations for nearest-WTW fallback (approximate, for unconfirmed wards)
_WTW_LOCS = [
    (-25.804, 28.752, 74.0),  # Bronkhorstpruit Town WTW
    (-25.413, 28.258, 73.3),  # Pretoria Temba WTW
    (-25.688, 28.539, 53.6),  # Onverwacht borehole
    (-25.872, 28.702, 41.5),  # Bronkhorstbaai WTW
    (-25.387, 28.250, 39.5),  # Klipdrift WTW (Magalies)
    (-25.631, 28.371, 38.1),  # Roodeplaat WTW (Pretoria North)
    (-25.512, 29.020, 35.5),  # Sokhulumi borehole
    (-25.747, 28.188, 34.6),  # Pretoria Findlay (Fountains)
    (-25.832, 28.283, 31.9),  # Rietvlei WTW (Pretoria Central & South)
    (-25.566, 28.302, 27.5),  # Walmansthal WTW (Magalies)
    (-25.671, 28.524, 24.5),  # Cullinan WTW (Magalies)
    (-25.810, 28.750, 24.0),  # Summerplace WTW
]

KNOWN_CHOKEPOINTS = [
    "TSH_58",   # Bosman Station corridor — 1000mm HDPE: 4+ confirmed bursts (2024, 2025 x2, 2026)
    "TSH_80",   # Salvokop — same trunk main, different ward: 2 confirmed bursts (INC-2020-001, INC-2020-002)
    # TSH_59 (Fountains) deliberately excluded: 1 confirmed burst (INC-2019-001) on the same pipe
    # but 1 incident does not establish a ward as a repeat-failure chokepoint.
    # Re-evaluate if a second TSH_59 burst is confirmed.
]

# Column-name detection for the LABELED INCIDENTS CSV (output of define_target.py).
# WardLabel holds the "TSH_XX" format directly — WardID is a different field (the
# raw numeric MDB code) and is deliberately excluded here to avoid a silent mix-up.
WARD_COL_CANDIDATES = ["WardLabel", "ward_id", "ward_label", "ward"]
DATE_COL_CANDIDATES = ["date_start", "date", "incident_date", "release_date", "Date"]

# The wards geojson has a confirmed "WardLabel" column (e.g. "TSH_58") directly —
# same field name and format as the incidents CSV's ward column. No derivation needed.


def detect_col(df, candidates, label):
    for c in candidates:
        if c in df.columns:
            return c
    raise KeyError(
        f"Could not find a {label} column. Looked for: {candidates}. "
        f"Available columns: {list(df.columns)}"
    )


def load_incidents() -> pd.DataFrame:
    df = pd.read_csv(LABELED_INCIDENTS_FILE)
    ward_col = detect_col(df, WARD_COL_CANDIDATES, "ward ID")
    date_col = detect_col(df, DATE_COL_CANDIDATES, "date")

    df = df.rename(columns={ward_col: "ward_id", date_col: "date"})
    df["date"] = pd.to_datetime(df["date"])
    df["month"] = df["date"].dt.to_period("M")

    for needed in ["infra_failure_tshwane", "supply_disrupted_external"]:
        if needed not in df.columns:
            raise KeyError(f"Expected '{needed}' column — run define_target.py first.")

    keep = ["ward_id", "date", "month", "infra_failure_tshwane", "supply_disrupted_external"]
    if "category_role" in df.columns:
        keep.append("category_role")
    return df[keep]


def load_ward_list() -> pd.DataFrame:
    gdf = gpd.read_file(WARDS_GEOJSON_FILE)

    if "WardLabel" not in gdf.columns:
        raise KeyError(
            f"Expected a 'WardLabel' column (e.g. 'TSH_58') in the wards geojson. "
            f"Found columns: {list(gdf.columns)}"
        )
    gdf["ward_id"] = gdf["WardLabel"]

    # Per project notes, this file is already EPSG:4326 — set it explicitly only if
    # the geojson has no CRS metadata, otherwise reproject from whatever it actually is.
    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=4326)

    # Area in km^2 — reproject to UTM 35S (metric) before measuring
    gdf_m = gdf.to_crs(epsg=32735)
    gdf["area_km2"] = gdf_m.geometry.area / 1e6

    return gdf[["ward_id", "area_km2"]].drop_duplicates(subset="ward_id")


def months_since_last_failure(s: pd.Series) -> pd.Series:
    out = np.full(len(s), 999)
    last_seen = -999
    for i, val in enumerate(s.values):
        if val == 1:
            last_seen = i
        out[i] = (i - last_seen) if last_seen != -999 else 999
    return pd.Series(out, index=s.index)


def forward_failure_within(s: pd.Series, window: int) -> pd.Series:
    """1 if any of the next `window` months has a failure, NaN if that
    forward window isn't fully observed yet (right-censored)."""
    shifted = [s.shift(-i) for i in range(1, window + 1)]
    stacked = pd.concat(shifted, axis=1)
    has_full_window = stacked.notna().all(axis=1)
    target = stacked.max(axis=1)
    target[~has_full_window] = np.nan
    return target


def build_panel(incidents: pd.DataFrame, wards: pd.DataFrame) -> pd.DataFrame:
    all_months = pd.period_range(incidents["month"].min(), incidents["month"].max(), freq="M")

    panel = pd.MultiIndex.from_product(
        [wards["ward_id"], all_months], names=["ward_id", "month"]
    ).to_frame(index=False)
    panel = panel.merge(wards, on="ward_id", how="left")

    monthly_failures = (
        incidents[incidents["infra_failure_tshwane"] == 1]
        .groupby(["ward_id", "month"])
        .size()
        .reset_index(name="failure_count_this_month")
    )
    panel = panel.merge(monthly_failures, on=["ward_id", "month"], how="left")
    panel["failure_count_this_month"] = panel["failure_count_this_month"].fillna(0).astype(int)
    panel["failure_occurred_this_month"] = (panel["failure_count_this_month"] > 0).astype(int)
    panel = panel.sort_values(["ward_id", "month"]).reset_index(drop=True)

    # --- Features available without new data (no leakage — past/current only) ---
    panel["cumulative_failures_to_date"] = (
        panel.groupby("ward_id")["failure_occurred_this_month"].cumsum()
    )
    panel["months_since_last_failure"] = (
        panel.groupby("ward_id")["failure_occurred_this_month"]
        .transform(months_since_last_failure)
    )
    panel["is_known_chokepoint"] = panel["ward_id"].isin(KNOWN_CHOKEPOINTS).astype(int)
    panel["calendar_month"] = panel["month"].apply(lambda p: p.month)
    panel["is_dry_season"] = panel["calendar_month"].isin([5, 6, 7, 8, 9]).astype(int)  # May-Sep

    # --- Municipal-level constant features (same value all rows/wards/months) ---
    # NRW: Non-Revenue Water % for City of Tshwane, 2021/22 financial year.
    # Source: DWS Blue Drop Report 2023 (Gauteng), p.52 — official regulatory audit figure.
    # Currently a municipal-level constant (no ward-level or year-by-year breakdown available).
    # As a constant it carries zero intra-panel variance so XGBoost will not use it for
    # splitting — its SHAP contribution will be 0. The column is recorded here so that:
    #   (a) the data point is formally documented in the pipeline, and
    #   (b) if ward-level or time-varying NRW data arrives later, the column is already in place.
    # Replace with a time-varying or ward-varying series once that data is obtained from
    # datahub@tshwane.gov.za or the IMQS Pipe Priority Program export.
    panel["nrw_pct"] = 33.0

    # WSS BDRR: ward-varying water supply system Blue Drop Risk Rating.
    # 14 wards confirmed via geocoding; remainder via nearest-WTW Euclidean distance.
    # Does NOT vary over time (2024/2025 BDRR used as a static proxy).
    # Caution: BDRR measures water quality management risk, not pipe failure risk directly.
    # The correlation is via management culture: poor compliance tends to correlate with
    # poor maintenance, which in turn correlates with pipe deterioration.
    # See WSS_BDRR_LOOKUP + _WTW_LOCS at top of file for full methodology notes.
    def _ward_bdrr(ward_id, centroid_lat, centroid_lon):
        if ward_id in WSS_BDRR_LOOKUP:
            return WSS_BDRR_LOOKUP[ward_id]
        # Nearest-WTW fallback: Euclidean distance on lat/lon (approximate)
        best = min(_WTW_LOCS, key=lambda t: (centroid_lat - t[0])**2 + (centroid_lon - t[1])**2)
        return best[2]

    # Load ward centroids (projected for accuracy) for nearest-WTW assignment
    gdf_bdrr = gpd.read_file(WARDS_GEOJSON_FILE)
    if gdf_bdrr.crs is None:
        gdf_bdrr = gdf_bdrr.set_crs(epsg=4326)
    gdf_bdrr["ward_id"] = gdf_bdrr["WardLabel"]
    gdf_proj = gdf_bdrr.to_crs(epsg=32735)
    centroids_proj = gdf_proj.geometry.centroid.to_crs(epsg=4326)
    gdf_bdrr["c_lat"] = centroids_proj.y
    gdf_bdrr["c_lon"] = centroids_proj.x
    centroid_lookup = {row["ward_id"]: (row["c_lat"], row["c_lon"])
                       for _, row in gdf_bdrr.iterrows()}

    panel["wss_bdrr"] = panel["ward_id"].map(
        lambda w: _ward_bdrr(w, *centroid_lookup.get(w, (0.0, 0.0)))
    )

    # --- Forward-looking early-warning target ---
    panel["failure_within_3mo"] = (
        panel.groupby("ward_id")["failure_occurred_this_month"]
        .transform(lambda s: forward_failure_within(s, LEAD_WINDOW_MONTHS))
    )

    before = len(panel)
    panel = panel.dropna(subset=["failure_within_3mo"]).copy()
    panel["failure_within_3mo"] = panel["failure_within_3mo"].astype(int)
    print(f"Dropped {before - len(panel)} ward-months with incomplete forward window (right-censored).")

    panel["month"] = panel["month"].astype(str)
    return panel


def summarize(panel: pd.DataFrame):
    n_rows = len(panel)
    n_pos = int(panel["failure_within_3mo"].sum())
    print(f"\nPanel rows (ward-months):        {n_rows}")
    print(f"Positive examples (target=1):    {n_pos}  ({n_pos / n_rows:.2%})")
    print(f"Wards represented:               {panel['ward_id'].nunique()}")
    print(
        "\n⚠ FEATURE LIMITATION: nrw_pct=33.0 (Blue Drop 2023, municipal constant — zero variance). "
        "wss_bdrr added (BD PAT 2025, ward-varying, 14 confirmed + 93 nearest-WTW). "
        "Pipe age, material, and maintenance data still pending (IMQS Pipe Priority Program "
        "export via datahub@tshwane.gov.za). Treat model as recency/management-proxy baseline."
    )


def main():
    if not LABELED_INCIDENTS_FILE.exists():
        raise FileNotFoundError(f"Missing {LABELED_INCIDENTS_FILE} — run define_target.py first.")
    if not WARDS_GEOJSON_FILE.exists():
        raise FileNotFoundError(f"Missing {WARDS_GEOJSON_FILE} — update WARDS_GEOJSON_FILE path.")

    incidents = load_incidents()
    wards = load_ward_list()

    unmatched = set(incidents["ward_id"]) - set(wards["ward_id"])
    if unmatched:
        nan_count = sum(1 for w in unmatched if pd.isna(w))
        string_mismatches = sorted(str(w) for w in unmatched if not pd.isna(w))

        if nan_count:
            null_rows = incidents[incidents["ward_id"].isna()]
            # Suppress warning for rows already intentionally excluded
            if "category_role" in null_rows.columns:
                unresolved = null_rows[~null_rows["category_role"].str.startswith("excluded_", na=False)]
            else:
                unresolved = null_rows
            if not unresolved.empty:
                affected_ids = unresolved.index.tolist()
                print(
                    f"⚠ {len(affected_ids)} incident(s) have a MISSING ward assignment (NaN) — these rows "
                    "will be silently dropped from the panel since they can't be matched to any "
                    "ward. Their failures won't be counted anywhere. Check the source CSV's WardLabel "
                    f"column for the row(s) at index {affected_ids} and re-run the ward-tagging/geocode "
                    "step for them before trusting panel output."
                )
            # All null-WardLabel rows are excluded categories — no action needed
        if string_mismatches:
            print(
                f"⚠ {len(string_mismatches)} ward_id(s) in incidents not found in the ward list — "
                f"likely a formatting mismatch (e.g. zero-padding): {string_mismatches}"
            )

    panel = build_panel(incidents, wards)
    summarize(panel)

    # ── Hard validation guards ────────────────────────────────────────────────
    _errors = []
    n_wards = panel["ward_id"].nunique()
    expected_wards = _cfg.N_WARDS if _cfg else 107
    if n_wards != expected_wards:
        _errors.append(f"Ward count {n_wards} ≠ {expected_wards} — check ward join.")
    if panel.duplicated(subset=["ward_id", "month"]).any():
        n_dups = panel.duplicated(subset=["ward_id", "month"]).sum()
        _errors.append(f"{n_dups} duplicate ward×month rows detected.")
    for feat in ["area_km2", "wss_bdrr", "pop_density"]:
        if feat in panel.columns:
            null_rate = panel[feat].isna().mean()
            max_null = _cfg.MAX_NULL_RATE if _cfg else 0.05
            if null_rate > max_null:
                _errors.append(f"{feat} null rate {null_rate:.1%} exceeds {max_null:.0%} threshold.")
    if "pop_density" in panel.columns and (panel["pop_density"] < 0).any():
        _errors.append("Negative pop_density values found — check census_2011_ward_population.csv.")
    if _errors:
        for e in _errors:
            print(f"✗  VALIDATION FAILED: {e}")
        raise SystemExit("Panel failed validation. Fix errors above before training.")
    print("✓  Validation passed.")
    # ─────────────────────────────────────────────────────────────────────────

    panel.to_csv(OUTPUT_FILE, index=False)
    print(f"\nSaved panel to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
