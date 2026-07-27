import json
from html import unescape
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
INTERIM_DIR = PROJECT_ROOT / "data" / "interim"
INTERIM_DIR.mkdir(parents=True, exist_ok=True)

def strip_html(raw_html):
    text = unescape(raw_html or "")
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

with open(RAW_DIR / "tshwane_media_releases_water_filtered.json", "r", encoding="utf-8") as f:
    media = json.load(f)

with open(RAW_DIR / "tshwane_service_interruptions_raw.json", "r", encoding="utf-8") as f:
    interruptions = json.load(f)

interruption_ids = {p["id"] for p in interruptions}

CUTOFF = "2024-03-18"  # earliest post in the Service Interruptions category

overlap = []
new_pre_cutoff = []
new_post_cutoff = []

for p in media:
    if p["id"] in interruption_ids:
        overlap.append(p)
    elif p["date"][:10] < CUTOFF:
        new_pre_cutoff.append(p)
    else:
        new_post_cutoff.append(p)

print(f"Total water-related media releases: {len(media)}")
print(f"  Overlap with Service Interruptions (already have):  {len(overlap)}")
print(f"  New, pre-March-2024 (genuinely new historical ground): {len(new_pre_cutoff)}")
print(f"  New, post-March-2024 but NOT in Service Interruptions: {len(new_post_cutoff)}")

print("\n--- New pre-2024 posts (sorted oldest first) ---")
for p in sorted(new_pre_cutoff, key=lambda x: x["date"]):
    print(f"  [{p['date'][:10]}] {strip_html(p['title']['rendered'])}")

print("\n--- New post-2024 posts NOT in Service Interruptions (potentially distinct failure events) ---")
for p in sorted(new_post_cutoff, key=lambda x: x["date"]):
    print(f"  [{p['date'][:10]}] {strip_html(p['title']['rendered'])}")

with open(INTERIM_DIR / "tshwane_media_releases_new_pre2024.json", "w", encoding="utf-8") as f:
    json.dump(new_pre_cutoff, f, ensure_ascii=False, indent=2)

with open(INTERIM_DIR / "tshwane_media_releases_new_post2024.json", "w", encoding="utf-8") as f:
    json.dump(new_post_cutoff, f, ensure_ascii=False, indent=2)

print(f"\nSaved {len(new_pre_cutoff)} pre-2024 posts -> tshwane_media_releases_new_pre2024.json")
print(f"Saved {len(new_post_cutoff)} post-2024 posts -> tshwane_media_releases_new_post2024.json")