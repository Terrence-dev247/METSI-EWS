import csv
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
INTERIM_DIR = PROJECT_ROOT / "data" / "interim"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

NEW_INCIDENTS = INTERIM_DIR / "tshwane_incident_candidates_final_wardtagged.csv"
BATCH1 = INTERIM_DIR / "tshwane_water_incidents_batch1_wardtagged.csv"
OUTPUT_FILE = PROCESSED_DIR / "tshwane_water_incidents_combined.csv"

# Per-incident overrides, keyed by a distinctive title substring.
# Fields: category, asset_type, suspected_cause, status
OVERRIDES = {
    "EMERGENCY WATER SUPPLY INTERRUPTION: BRONKHORSTSPRUIT WATER PURIFICATION PLANT": dict(
        category="unplanned_unspecified",
        asset_type="Bronkhorstspruit Water Purification Plant",
        suspected_cause="not stated in source (plant-level emergency interruption)",
        status="presumed resolved (not confirmed in source)"),
    "Vandalism affecting pipelines to Rand Water": dict(
        category="vandalism",
        asset_type="not stated in source / pending notes review",
        suspected_cause="vandalism affecting Rand Water booster station pipelines",
        status="presumed resolved (not confirmed in source)"),
    "Emergency shutdown of water supply to Mabopane Block UX": dict(
        category="unplanned_unspecified",
        asset_type="not stated in source",
        suspected_cause="not stated in source (emergency shutdown)",
        status="presumed resolved (not confirmed in source)"),
    "EMERGENCY REPAIRS TO RAND WATER B8 PIPELINE WATER LEAK": dict(
        category="unplanned_burst",
        asset_type="Rand Water B8 bulk pipeline",
        suspected_cause="pipeline leak",
        status="excluded_external_bulk_supply"),  # Rand Water's OWN pipeline (Zuikerbosch-Mapleton),
                                                     # not Tshwane's asset -- category describes failure
                                                     # TYPE accurately, status flags ownership/location.
                                                     # (Found: this was "unplanned_burst" + default status
                                                     # before, which silently counted it as a Tshwane
                                                     # positive on a from-scratch rerun -- the previous
                                                     # correct exclusion must have been a direct edit to
                                                     # the output CSV that was never written back here.)
    "Urgent repair of Laudium Reservoir main feeder pipe": dict(
        category="unplanned_burst",
        asset_type="Laudium Reservoir main feeder pipe",
        suspected_cause="not stated in source (urgent pipe repair)",
        status="presumed resolved (not confirmed in source)"),
    "COMMUNITIES IN HAMMANSKRAAL AND SURROUNDING AREAS URGED NOT TO DRINK WATER": dict(
        category="quality_shutdown",
        asset_type="Temba Water Treatment Works (raw-water quality) -- original May 2023 cholera outbreak warning",
        suspected_cause="cholera outbreak linked to contaminated piped water",
        status="resolved"),
    "Emergency repairs on the water supply pipeline in Leeuwfontein": dict(
        category="unplanned_burst",
        asset_type="water supply pipeline, Leeuwfontein",
        suspected_cause="not stated in source (emergency pipeline repair)",
        status="presumed resolved (not confirmed in source)"),
    "Tshwane affected by power failures impacting on Rand Water supply infrastructure": dict(
        category="power_failure",
        asset_type="Rand Water bulk supply infrastructure (unspecified station)",
        suspected_cause="power failure affecting Rand Water bulk supply",
        status="presumed resolved (not confirmed in source)"),
    "Power trip at Mapleton Booster Pumping Station": dict(
        category="power_failure",
        asset_type="Rand Water Mapleton Booster Pumping Station (outside Tshwane)",
        suspected_cause="power trip",
        status="presumed resolved (not confirmed in source)"),
    "Unplanned water supply interruption affecting several parts in Region 3": dict(
        category="unplanned_unspecified",
        asset_type="not stated in source",
        suspected_cause="not stated in source",
        status="presumed resolved (not confirmed in source)"),
    "Power dip affecting the Rand Water Zuikerbosch Treatment Plant": dict(
        category="power_failure",
        asset_type="Rand Water Zuikerbosch Treatment Plant (outside Tshwane)",
        suspected_cause="power dip",
        status="resolved"),
    "Rand Water\u2019s Zuikerbosch Water Treatment Plant affected by severe thunderstorm": dict(
        category="weather_related",
        asset_type="Rand Water Zuikerbosch Treatment Plant (outside Tshwane)",
        suspected_cause="severe thunderstorm damage",
        status="presumed resolved (not confirmed in source)"),
    "Unplanned water supply interruption affecting Mamelodi and nearby areas": dict(
        category="unplanned_unspecified",
        asset_type="not stated in source",
        suspected_cause="not stated in source",
        status="presumed resolved (not confirmed in source)"),
    "Update: Unplanned water supply interruption affecting Queenswood and nearby areas": dict(
        category="unplanned_unspecified",
        asset_type="not stated in source",
        suspected_cause="not stated in source",
        status="presumed resolved (not confirmed in source)"),
    "Unplanned water supply interruption affecting Mamelodi and Eersterust": dict(
        category="unplanned_unspecified",
        asset_type="not stated in source",
        suspected_cause="not stated in source",
        status="presumed resolved (not confirmed in source)"),
    "Vandalism and cable theft at Temba Waste Water Treatment Works": dict(
        category="vandalism",
        asset_type="Temba Waste Water Treatment Works -- cable/infrastructure theft",
        suspected_cause="vandalism / cable theft",
        status="presumed resolved (not confirmed in source)"),
    "City of Tshwane condemns possible sabotage of water infrastructure in Rethabiseng": dict(
        category="vandalism",
        asset_type="not stated in source",
        suspected_cause="suspected sabotage",
        status="presumed resolved (not confirmed in source)"),
    "Power failure affecting operations at Bronkhorstspruit Water Treatment Plant": dict(
        category="power_failure",
        asset_type="Bronkhorstspruit Water Treatment Plant",
        suspected_cause="power failure",
        status="presumed resolved (not confirmed in source)"),
    "Continuation of emergency repairs to a bulk pipeline which supplies Zithobeni Reservoir": dict(
        category="unplanned_burst",
        asset_type="bulk pipeline supplying Zithobeni Reservoir",
        suspected_cause="not stated in source (emergency pipeline repair)",
        status="presumed resolved (not confirmed in source)"),
    "Urgent shutdown of water supply to Rosslyn and nearby areas": dict(
        category="unplanned_unspecified",
        asset_type="not stated in source",
        suspected_cause="not stated in source",
        status="presumed resolved (not confirmed in source)"),
    "Update on City of Tshwane reservoirs that were affected by Rand Water\u2019s Palmiet Booster Station power trip": dict(
        category="power_failure",
        asset_type="Rand Water Palmiet Booster Pumping Station (outside Tshwane)",
        suspected_cause="power trip",
        status="presumed resolved (not confirmed in source)"),
    "Tampering with critical gas and water infrastructure": dict(
        category="vandalism",
        asset_type="Rand Water and SASOL bulk pipeline markings, Sekampaneng Ridge/Suurman",
        suspected_cause="theft of ferrous metals from pipeline infrastructure",
        status="presumed resolved (not confirmed in source)"),
    "City of Tshwane reservoirs still at extremely low levels": dict(
        category="unplanned_unspecified",
        asset_type="not stated in source (downstream effect)",
        suspected_cause="Rand Water Palmiet Booster Pump Station power trip (external)",
        status="excluded_external_bulk_supply"),  # downstream-effects post about an external
                                                     # Rand Water power trip, same pattern as the
                                                     # Palmiet/Mapleton entries above
    "Temba Water Treatment Works to remain off pending raw water test results": dict(
        category="quality_shutdown",
        asset_type="Temba Water Treatment Plant (Tshwane-owned)",
        suspected_cause="sewage contamination of upstream dam, traced to a substation fire",
        status="presumed resolved (not confirmed in source)"),  # water-quality mechanism, not
                                                                    # pipe/structural fatigue -- same
                                                                    # principle as Hammanskraal/Temba
                                                                    # contamination already excluded
    "Temporary shutdown of Bronkhorstspruit Water Treatment Plant": dict(
        category="quality_shutdown",
        asset_type="Bronkhorstspruit Water Treatment Plant (Tshwane-owned)",
        suspected_cause="deteriorated raw water quality after heavy rains",
        status="presumed resolved (not confirmed in source)"),  # raw-water-quality mechanism (rain-driven
                                                                    # turbidity), not pipe/structural fatigue --
                                                                    # distinct from the Feb-2023 equipment-failure
                                                                    # event at the same plant (51483, kept as
                                                                    # target_positive -- that one IS a structural
                                                                    # asset failure, not a quality issue)
    "Planned water supply shutdown to the Meintjieskop and Hospital Reservoirs": dict(
        category="unplanned_burst",
        asset_type="Meintjieskop/Hospital Reservoir bulk supply pipe (Tshwane-owned)",
        suspected_cause="major leak on bulk pipe",
        status="presumed resolved (not confirmed in source)"),  # title says "planned shutdown" but body
                                                                    # describes a major leak -- the shutdown
                                                                    # window was scheduled, the leak wasn't
}

SCOPE_TO_REGION_TEXT = {
    "localized": None,  # filled from WardLabel directly
    "outside_tshwane": "Outside Tshwane metro boundary (Rand Water bulk infrastructure) - not ward-applicable",
    "bulk_supply_metro_wide": "Metro-wide impact via bulk supply chain - no single ward applies",
    "multi_ward": "Spans multiple wards within a Region - needs manual GIS overlay if ward-level detail required",
    "needs_review": "Area not yet identified from notes - pending manual review",
}

with open(NEW_INCIDENTS, "r", encoding="utf-8") as f:
    new_rows = list(csv.DictReader(f))

target_fieldnames = ["incident_id", "category", "date_start", "date_end", "date_confidence",
                      "status", "primary_area", "areas_affected", "region_or_ward", "asset_type",
                      "suspected_cause", "source_name", "source_url", "notes", "lat", "lon",
                      "geocode_precision", "WardID", "WardLabel"]

transformed = []
year_counters = {}

for r in new_rows:
    override = None
    for substring, vals in OVERRIDES.items():
        if substring in r["title"]:
            override = vals
            break
    if override is None:
        override = dict(category="unplanned_unspecified", asset_type="not stated in source",
                         suspected_cause="not stated in source",
                         status="presumed resolved (not confirmed in source)")

    year = r["date"][:4]
    year_counters[year] = year_counters.get(year, 100) + 1
    new_id = f"INC-{year}-{year_counters[year]}"

    scope = r.get("scope", "")
    region_text = SCOPE_TO_REGION_TEXT.get(scope)
    if region_text is None:  # localized -> use actual ward
        region_text = f"{r.get('WardLabel', '') or 'ward TBD'} (geocoded)"

    geocode_precision = ""
    if r.get("lat"):
        geocode_precision = "area-centroid (Google Places) - NOT exact incident location, good enough for ward tagging only"

    transformed.append({
        "incident_id": new_id,
        "category": override["category"],
        "date_start": r["date"][:10],
        "date_end": "",
        "date_confidence": "confirmed (official City media release)",
        "status": override["status"],
        "primary_area": r.get("primary_area", "") or "not applicable - see notes/scope",
        "areas_affected": r["title"],
        "region_or_ward": region_text,
        "asset_type": override["asset_type"],
        "suspected_cause": override["suspected_cause"],
        "source_name": "City of Tshwane (official media release)",
        "source_url": r["source_url"],
        "notes": r["notes"] + f" [scope={scope}; geocode_flag={r.get('geocode_flag','')}]",
        "lat": r.get("lat", ""),
        "lon": r.get("lon", ""),
        "geocode_precision": geocode_precision,
        "WardID": r.get("WardID", ""),
        "WardLabel": r.get("WardLabel", ""),
    })

with open(BATCH1, "r", encoding="utf-8") as f:
    batch1_rows = list(csv.DictReader(f))

all_rows = batch1_rows + transformed

with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=target_fieldnames)
    writer.writeheader()
    writer.writerows(all_rows)

print(f"Wrote {OUTPUT_FILE}")
print(f"  batch1 rows: {len(batch1_rows)}")
print(f"  new rows added: {len(transformed)}")
print(f"  total: {len(all_rows)}")

from collections import Counter
print("\nCategory breakdown (new rows only):")
for cat, count in Counter(r["category"] for r in transformed).most_common():
    print(f"  {cat}: {count}")

dates = sorted(r["date_start"] for r in all_rows if r["date_start"])
print(f"\nCombined date range: {dates[0]} to {dates[-1]}")
