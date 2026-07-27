"""
One-off data-cleaning patch — already applied. Kept for historical reference.
"""
import csv
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
INTERIM_DIR = PROJECT_ROOT / "data" / "interim"
INPUT_FILE = INTERIM_DIR / "tshwane_water_incidents_batch1_wardtagged.csv"

with open(INPUT_FILE, "r", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))
    fieldnames = list(rows[0].keys())

fixed_count = 0
for r in rows:
    if "x" in r["date_start"].lower() and r["date_start"][:7] == "2026-06":
        old_date = r["date_start"]
        old_confidence = r["date_confidence"]
        r["date_start"] = "2026-06-22"
        r["date_confidence"] = ("approximate (using data-pull/snapshot date of 2026-06-22; "
                                 "exact incident start date not isolated from source)")
        fixed_count += 1
        print(f"{r['incident_id']}: date_start '{old_date}' -> '2026-06-22'")
        print(f"  date_confidence: '{old_confidence}'")
        print(f"               -> '{r['date_confidence']}'")

with open(INPUT_FILE, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

print(f"\nFixed {fixed_count} row(s) in {INPUT_FILE}")
