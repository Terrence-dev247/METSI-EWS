import csv
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
INTERIM_DIR = PROJECT_ROOT / "data" / "interim"

INPUT_FILE = INTERIM_DIR / "tshwane_incident_candidates_final.csv"
OUTPUT_FILE = INTERIM_DIR / "tshwane_incident_candidates_final_geocoded.csv"

# (title substring to match, primary_area, lat, lon, scope, flag)
# scope values:
#   localized            -> genuine point-failure inside a Tshwane ward, geocoded
#   outside_tshwane       -> Rand Water's own bulk infrastructure, physically
#                            outside Tshwane (Zuikerbosch/Vereeniging, Mapleton
#                            and Palmiet near southern Johannesburg)
#   bulk_supply_metro_wide -> affects Tshwane broadly via the bulk supply chain,
#                            no single point applies
#   multi_ward            -> within Tshwane but spans a whole administrative
#                            Region, not a single point
#   needs_review           -> title alone doesn't name a specific area; check
#                            the full "notes" column manually
MAPPING = [
    ("EMERGENCY WATER SUPPLY INTERRUPTION: BRONKHORSTSPRUIT WATER PURIFICATION PLANT",
     "Bronkhorstspruit", -25.8048502, 28.7524051, "localized", ""),
    ("Vandalism affecting pipelines to Rand Water",
     "", "", "", "needs_review", "Check notes column for the specific pipeline/area named"),
    ("Emergency shutdown of water supply to Mabopane Block UX",
     "Mabopane", -25.5130652, 28.0402843, "localized", ""),
    ("EMERGENCY REPAIRS TO RAND WATER B8 PIPELINE WATER LEAK",
     "", "", "", "needs_review", "Check notes column for which suburb the B8 pipeline serves"),
    ("Urgent repair of Laudium Reservoir main feeder pipe",
     "Laudium", -25.7835856, 28.0976369, "localized", ""),
    ("COMMUNITIES IN HAMMANSKRAAL AND SURROUNDING AREAS URGED NOT TO DRINK WATER",
     "Hammanskraal", -25.4131348, 28.2579513, "localized",
     "POSSIBLE DUPLICATE -- check this isn't already in batch1 (May 2023 cholera outbreak)"),
    ("Emergency repairs on the water supply pipeline in Leeuwfontein",
     "Leeuwfontein", -25.6623247, 28.3824016, "localized", ""),
    ("Tshwane affected by power failures impacting on Rand Water supply infrastructure",
     "", "", "", "bulk_supply_metro_wide", "Affects Tshwane broadly via bulk supply chain, no single point"),
    ("Power trip at Mapleton Booster Pumping Station",
     "", "", "", "outside_tshwane", "Mapleton is ~50km south, near southern Johannesburg"),
    ("Unplanned water supply interruption affecting several parts in Region 3",
     "Waterkloof (Jan Shoba St)", -25.7553876, 28.2395099, "localized",
     "Per needs_review notes: has a clean single point (Waterkloof Reservoir, Jan Shoba "
     "St repair site) despite the multi-suburb affected list -- same single-point-repair-with-"
     "multi-suburb-impact pattern as other localized incidents. Previously mis-set to "
     "'multi_ward' (no lat/lon), which silently dropped this target_positive incident from "
     "the panel entirely -- the notes file already recommended this fix but it was never "
     "applied to the script."),
    ("Power dip affecting the Rand Water Zuikerbosch Treatment Plant",
     "", "", "", "outside_tshwane", "Zuikerbosch is in Vereeniging"),
    ("Rand Water\u2019s Zuikerbosch Water Treatment Plant affected by severe thunderstorm",
     "", "", "", "outside_tshwane", "Zuikerbosch is in Vereeniging"),
    ("Unplanned water supply interruption affecting Mamelodi and nearby areas",
     "Mamelodi", -25.7234441, 28.4221519, "localized", ""),
    ("Update: Unplanned water supply interruption affecting Queenswood and nearby areas",
     "Queenswood", -25.7281389, 28.2515389, "localized", ""),
    ("Unplanned water supply interruption affecting Mamelodi and Eersterust",
     "Mamelodi", -25.7234441, 28.4221519, "localized", "Also affected Eersterust -- secondary area not geocoded"),
    ("Vandalism and cable theft at Temba Waste Water Treatment Works",
     "Temba", -25.4037577, 28.2665085, "localized", ""),
    ("City of Tshwane condemns possible sabotage of water infrastructure in Rethabiseng",
     "Rethabiseng", -25.7228592, 28.7168850, "localized", ""),
    ("Power failure affecting operations at Bronkhorstspruit Water Treatment Plant",
     "Bronkhorstspruit", -25.8048502, 28.7524051, "localized", ""),
    ("Continuation of emergency repairs to a bulk pipeline which supplies Zithobeni Reservoir",
     "Zithobeni", -25.782674, 28.7212582, "localized", ""),
    ("Urgent shutdown of water supply to Rosslyn and nearby areas",
     "Rosslyn", -25.6269091, 28.0963666, "localized", ""),
    ("Update on City of Tshwane reservoirs that were affected by Rand Water\u2019s Palmiet Booster Station power trip",
     "", "", "", "outside_tshwane", "Palmiet is ~50km south, near southern Johannesburg"),
    ("Tampering with critical gas and water infrastructure",
     "Hammanskraal (approx.)", -25.4131348, 28.2579513, "localized",
     "Approximate -- specific site was Sekampaneng Ridge/Suurman, not separately geocodable"),
    # --- Batch 2 additions (body-aware classify() fix + manual news-search review) ---
    ("Update on parts of Region 2 affected by water interruptions",
     "Montana", -25.6713549, 28.243326, "localized", "Ruptured pipeline in Montana, Region 2; second leak detected days later"),
    ("Bronkhorstspruit Water Treatment Plant operating at low capacity",
     "Bronkhorstspruit", -25.8048502, 28.7524051, "localized", "Equipment failure at raw water pump station"),
    ("Water supply interruption affecting Mabopane and nearby areas",
     "Mabopane", -25.5130652, 28.0402843, "localized", "Major leak on 400mm pipeline near Odi Stadium, complicated by adjacent wetland"),
    ("Water supply interruption affecting Marabastad and nearby areas",
     "Marabastad", -25.7394229, 28.1758982, "localized", "Burst water pipe"),
    ("Water supply interruption affecting Sunnyside and surrounding areas",
     "Sunnyside / Salvokop", -25.760188, 28.1821197, "localized", "Continuous water leak in Salvokop Reservoir supply zone"),
    ("City of Tshwane responds to water supply challenges in some parts of Mabopane",
     "Mabopane", -25.5130652, 28.0402843, "localized", "Significant leak, Block C/D; electricity cable damaged during repair"),
    ("Temba Water Treatment Works to remain off pending raw water test results",
     "Temba", -25.4037577, 28.2665085, "localized", "Sewage contamination from upstream dam traced to a substation fire; plant shut down"),
    ("Water supply interruption affecting Soshanguve Block DD Reservoir",
     "Soshanguve", -25.4525229, 28.1088486, "localized", "Major crack discovered on supply pipeline, emergency repairs, both DD reservoirs drained"),
    ("Temporary shutdown of Bronkhorstspruit Water Treatment Plant",
     "Bronkhorstspruit", -25.8048502, 28.7524051, "localized", "Deteriorated raw water quality after heavy rains -- distinct from the Feb-2023 equipment-failure event"),
    ("Themba Water Treatment Plant still not fully functional",
     "Temba", -25.4037577, 28.2665085, "localized", "Power failure at raw water abstraction point on 2025-01-05; date set to failure date, not report date"),
    ("City of Tshwane prioritising Bronkhorstspruit water challenges",
     "Bronkhorstspruit", -25.8048502, 28.7524051, "localized",
     "PREDATES PANEL WINDOW (panel starts Oct 2022) -- leaks during a labour work-stoppage"),
    ("Water supply interruption in parts of Centurion",
     "Centurion (Gerhardsville)", -25.8524896, 28.0273914, "localized",
     "PREDATES PANEL WINDOW (panel starts Oct 2022) -- leaking pipe in Gerhardsville"),
    ("City of Tshwane reservoirs still at extremely low levels",
     "", "", "", "outside_tshwane", "Caused by Rand Water's Palmiet Booster Pump Station power trip -- same external bulk-supply pattern as other Palmiet/Mapleton entries"),
    ("Planned water supply shutdown to the Meintjieskop and Hospital Reservoirs",
     "Meintjieskop", -25.7403393, 28.2217382, "localized",
     "Major leak on bulk pipe supplying Meintjieskop/Hospital Reservoirs -- title's "
     "'planned shutdown' refers to the scheduled repair window for an already-discovered "
     "leak, not that the leak itself was planned"),
]

with open(INPUT_FILE, "r", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

for r in rows:
    matched = False
    for substring, area, lat, lon, scope, flag in MAPPING:
        if substring in r["title"]:
            r["primary_area"] = area
            r["lat"] = lat
            r["lon"] = lon
            r["scope"] = scope
            r["geocode_flag"] = flag
            matched = True
            break
    if not matched:
        r["primary_area"] = ""
        r["lat"] = ""
        r["lon"] = ""
        r["scope"] = "needs_review"
        r["geocode_flag"] = "NO TITLE MATCH -- script needs updating"

fieldnames = ["incident_id", "date", "title", "classification", "source_url", "notes",
              "primary_area", "lat", "lon", "scope", "geocode_flag"]

with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

from collections import Counter
print(f"Wrote {OUTPUT_FILE} -- {len(rows)} rows")
print("\nScope breakdown:")
for scope, count in Counter(r["scope"] for r in rows).most_common():
    print(f"  {scope}: {count}")

print("\nRows needing manual review or a flag to check:")
for r in rows:
    if r["geocode_flag"]:
        print(f"  [{r['date'][:10]}] {r['title'][:70]}... -- {r['geocode_flag']}")
