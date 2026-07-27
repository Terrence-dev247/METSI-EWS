"""
define_target.py

Builds the ML target variable for the METSI-EWS from
the real incident dataset's `category` column.

Why category-driven, not a single boolean flag:
  There is no pre-existing "excluded_external_bulk_supply" column in the combined
  CSV — that was an analytical finding, not stored data. The actual causal
  mechanism lives in `category`, and the dataset's own `notes` field flags at
  least THREE distinct mechanisms that should NOT count as Tshwane asset-fatigue
  failures:
    - power_failure    -> Rand Water bulk-supply infrastructure, outside Tshwane's
                          boundary (Ekurhuleni/Sedibeng) — not predictable from
                          Tshwane infra condition.
    - vandalism        -> security/criminal cause, not asset condition
                          (see INC-2026-003 notes: "exclude from pipe-failure
                          predictive target").
    - quality_shutdown -> raw-water contamination (e.g. Temba/Hammanskraal),
                          a water-quality mechanism, not pipe/structural fatigue
                          (see INC-2024-Q002 notes).

  Only `unplanned_burst` represents genuine Tshwane-owned pipe/asset structural
  failure — the thing the early-warning model is meant to predict.

Output columns added:
  - category_role             -> which bucket each row was routed to (for QA/audit)
  - infra_failure_tshwane     -> PRIMARY ML TARGET (1 only for unplanned_burst)
  - supply_disrupted_external -> contextual flag (power_failure), NOT a training label
  - vandalism_flag            -> contextual flag, NOT a training label
  - quality_shutdown_flag     -> contextual flag, NOT a training label

If a category appears that isn't in CATEGORY_ROLE_MAP below (e.g. a new
"planned_maintenance" category as more batches come in), the script will NOT
silently count it as a positive failure — it flags it for manual review and
excludes it by default. Update CATEGORY_ROLE_MAP once you've classified it.

Run:
    python define_target.py
"""

from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
INPUT_FILE = PROCESSED_DIR / "tshwane_water_incidents_combined.csv"
OUTPUT_FILE = PROCESSED_DIR / "tshwane_water_incidents_labeled.csv"

CATEGORY_ROLE_MAP = {
    "unplanned_burst": "target_positive",
    "unplanned_unspecified": "target_positive",  # unplanned + no other exclusion fits -> presumed
                                                   # Tshwane asset failure, mechanism just unspecified
                                                   # in source. Spot-check notes for these rows.
    "power_failure": "excluded_external_bulk_supply",
    "vandalism": "excluded_vandalism",
    "quality_shutdown": "excluded_quality_mechanism",
    "planned_maintenance": "excluded_planned_maintenance",  # scheduled work, not a failure
    "weather_related": "excluded_weather_related",          # exogenous environmental driver,
                                                              # separate hazard class
}


def build_target(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    if "category" not in df.columns:
        raise KeyError(f"Expected a 'category' column. Found columns: {list(df.columns)}")
    if "status" not in df.columns:
        raise KeyError(f"Expected a 'status' column. Found columns: {list(df.columns)}")

    roles = df["category"].map(CATEGORY_ROLE_MAP)

    unmapped = sorted(df.loc[roles.isna(), "category"].dropna().unique().tolist())
    if unmapped:
        print(
            f"⚠ Unmapped category value(s) found: {unmapped}\n"
            "  These are being excluded from the positive target by default.\n"
            "  Classify their causal mechanism and add them to CATEGORY_ROLE_MAP."
        )
        roles = roles.fillna("excluded_unmapped_category")

    # Some rows were manually flagged (status == "excluded_external_bulk_supply")
    # during earlier source-text review as actually being about Rand Water's OWN
    # infrastructure outside Tshwane's boundary — even when `category` alone
    # (e.g. "unplanned_burst", "vandalism", "weather_related") would suggest a
    # different bucket. category captures failure TYPE, not failure
    # LOCATION/OWNERSHIP — they aren't the same thing, and this manual flag is
    # the more authoritative signal since it required reading the source article.
    # It overrides the category-based role wherever present.
    is_external_flagged = df["status"] == "excluded_external_bulk_supply"
    n_overridden = int((is_external_flagged & (roles != "excluded_external_bulk_supply")).sum())
    if n_overridden:
        print(
            f"ℹ {n_overridden} row(s) had a category suggesting a different bucket, but are "
            "manually flagged as external bulk-supply (Rand Water's own infrastructure, "
            "outside Tshwane) based on source-text review — overriding category for these."
        )
    roles = roles.mask(is_external_flagged, "excluded_external_bulk_supply")

    df["category_role"] = roles
    df["infra_failure_tshwane"] = (roles == "target_positive").astype(int)
    df["supply_disrupted_external"] = (roles == "excluded_external_bulk_supply").astype(int)
    df["vandalism_flag"] = (roles == "excluded_vandalism").astype(int)
    df["quality_shutdown_flag"] = (roles == "excluded_quality_mechanism").astype(int)

    return df


def summarize(df: pd.DataFrame) -> None:
    n_total = len(df)
    print(f"Total incidents: {n_total}\n")
    print("Breakdown by role:")
    counts = df["category_role"].value_counts()
    for role, n in counts.items():
        print(f"  {role:35s} {n:3d}  ({n / n_total:.0%})")

    n_pos = int(df["infra_failure_tshwane"].sum())
    print(f"\nPrimary ML target positives (infra_failure_tshwane=1): {n_pos} / {n_total}")

    if n_pos < 30:
        print(
            f"\n⚠ Only {n_pos} positive examples in the dataset. This is thin for a "
            "standalone classifier — treat real-data model output as a risk-ranking "
            "tool calibrated against known chokepoints (e.g. TSH_58), not a "
            "high-confidence classifier, until incident volume grows."
        )


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"Could not find {INPUT_FILE}")

    df = pd.read_csv(INPUT_FILE)
    labeled = build_target(df)
    summarize(labeled)

    labeled.to_csv(OUTPUT_FILE, index=False)
    print(f"\nSaved labeled dataset to: {OUTPUT_FILE}")
    print("Use 'infra_failure_tshwane' as y in modeling. The other flag columns are context only.")


if __name__ == "__main__":
    main()
