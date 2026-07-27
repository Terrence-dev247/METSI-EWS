import csv
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
INTERIM_DIR = PROJECT_ROOT / "data" / "interim"

INPUT_FILE = INTERIM_DIR / "tshwane_incident_candidates.csv"
OUTPUT_FILE = INTERIM_DIR / "tshwane_incident_candidates_final.csv"

with open(INPUT_FILE, "r", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

# Not genuine water-infrastructure incidents -- general alerts, policy
# statements, or explicitly "no confirmed cases" type posts
EXCLUDE_SUBSTRINGS = [
    "Load-shedding, increased vandalism and theft",
    "prioritising critical infrastructure maintenance to reduce water leaks",
    "City to request urgent engagement with Rand Water on prolonged water supply issues",
    "closely monitoring current cholera outbreak",
    "on high alert following rising cholera cases in Gauteng",
    "calls on Rand Water to urgently address supply challenges",
    "high alert following cholera outbreak in Zimbabwe",
    "remains on alert to possible cholera outbreak",
    "carry out urgent upgrades on some bulk meters",
]

# Rolling updates / repeat posts about an event already captured by an
# earlier primary post -- dropped here, not lost (still in the raw JSON)
DROP_DUPLICATE_SUBSTRINGS = [
    "Emergency maintenance at Bronkhorstspruit Water Purification Plant",
    "LATEST UPDATE: VANDALISM AFFECTING PIPELINES",
    "UPDATE: CITY TESTING ON MULTIPLE SITES INDICATE ZERO CHOLERA",
    "Human Settlements Department ramps up water provision through water tankers to Hammanskraal after cholera outbreak",
    "Update on water outages after Rand Water\u2019s Zuikerbosch Water Treatment Plant was affected by severe thunderstorm",
    "Update at 12:30: Tshwane water supply continues to be affected by power failures",
    # Confirmed duplicate of INC-2024-106 (same Zithobeni bulk-pipeline burst,
    # this is just a later "Update:" post about the same event) -- found when
    # the body-aware classify() fix surfaced this post as a new candidate.
    "Update: Water supply interruption affecting Zithobeni and nearby areas",
]

AMBIGUOUS_SUBSTRING = "Tampering with critical gas and water infrastructure"

final_rows = []
ambiguous_row = None

for r in rows:
    title = r["title"]
    if AMBIGUOUS_SUBSTRING in title:
        ambiguous_row = r
        continue
    if any(sub in title for sub in EXCLUDE_SUBSTRINGS):
        continue
    if any(sub in title for sub in DROP_DUPLICATE_SUBSTRINGS):
        continue
    final_rows.append(r)

final_rows.sort(key=lambda x: x["date"])

with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=["incident_id", "date", "title", "classification", "source_url", "notes"])
    writer.writeheader()
    writer.writerows(final_rows)

print(f"Final deduplicated incident list: {len(final_rows)} rows -> {OUTPUT_FILE}")
print("\nFinal incidents:")
for r in final_rows:
    print(f"  [{r['date'][:10]}] {r['title']}")

if ambiguous_row:
    print("\n--- Ambiguous post, full text for your review ---")
    print(f"[{ambiguous_row['date'][:10]}] {ambiguous_row['title']}")
    print(ambiguous_row["notes"])
    print("\n(NOT included in the final CSV above. If, after reading this,")
    print("it describes a real tampering event rather than a general PSA,")
    print(f"add it manually to {OUTPUT_FILE}.)")
else:
    print("\nCould not find the ambiguous post by title match -- check manually.")
