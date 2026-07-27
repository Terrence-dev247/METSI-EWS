"""
Diagnostic/inspection script -- not part of regular pipeline reruns.
"""
import csv
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
INTERIM_DIR = PROJECT_ROOT / "data" / "interim"

with open(INTERIM_DIR / "tshwane_service_interruptions_parsed.csv", "r", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

def show(rows, label):
    print(f"\n=== {label} ({len(rows)} total) ===")
    for r in rows:
        print(f"\n--- id {r['incident_id']} | {r['date'][:10]} ---")
        print(f"Title: {r['title']}")
        print(f"Notes: {r['notes']}")

water_rows = [r for r in rows if r["utility"] == "water"]

unplanned = [r for r in water_rows if r["notice_type"] == "unplanned_failure"]
unclassified = [r for r in water_rows if r["notice_type"] == "unclassified"]

show(unplanned, "water / unplanned_failure")
show(unclassified, "water / unclassified")
