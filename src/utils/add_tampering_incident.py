"""
One-off patch script — already applied to the dataset. Kept for historical
reference, not part of regular pipeline reruns.
"""
import csv
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
INTERIM_DIR = PROJECT_ROOT / "data" / "interim"

CANDIDATES_FILE = INTERIM_DIR / "tshwane_incident_candidates.csv"
FINAL_FILE = INTERIM_DIR / "tshwane_incident_candidates_final.csv"

with open(CANDIDATES_FILE, "r", encoding="utf-8") as f:
    candidates = list(csv.DictReader(f))

target = next((r for r in candidates if "Tampering with critical gas and water infrastructure" in r["title"]), None)

if not target:
    print(f"Could not find the tampering post in {CANDIDATES_FILE} -- check manually.")
else:
    with open(FINAL_FILE, "r", encoding="utf-8") as f:
        final_rows = list(csv.DictReader(f))

    final_rows.append(target)
    final_rows.sort(key=lambda x: x["date"])

    with open(FINAL_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["incident_id", "date", "title", "classification", "source_url", "notes"])
        writer.writeheader()
        writer.writerows(final_rows)

    print(f"Added. {FINAL_FILE} now has {len(final_rows)} rows.")
