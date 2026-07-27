"""
Diagnostic/inspection script -- not part of regular pipeline reruns.
"""
import csv
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
INTERIM_DIR = PROJECT_ROOT / "data" / "interim"

with open(INTERIM_DIR / "tshwane_service_interruptions_parsed.csv", "r", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

def show(tag, n=2):
    matches = [r for r in rows if r["suspected_cause"] == tag]
    print(f"\n=== {tag} ({len(matches)} total) ===")
    for r in matches[:n]:
        print(f"\n--- id {r['incident_id']} | {r['date'][:10]} ---")
        print(f"Title: {r['title']}")
        print(f"Notes: {r['notes']}")

show("burst;leak;maintenance", n=3)
show("unclassified", n=3)
show("maintenance", n=2)
