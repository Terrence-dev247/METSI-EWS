import json
import re
import csv
from collections import Counter
from html import unescape
from pathlib import Path

# Renamed from parse_wp_posts.py for symmetry with pull_service_interruptions.py.
# Lives in <project_root>/src/pipeline/
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
INTERIM_DIR = PROJECT_ROOT / "data" / "interim"
INTERIM_DIR.mkdir(parents=True, exist_ok=True)

INPUT_FILE = RAW_DIR / "tshwane_service_interruptions_raw.json"
OUTPUT_FILE = INTERIM_DIR / "tshwane_service_interruptions_parsed.csv"

UTILITY_KEYWORDS = {
    "electricity": ["electricity supply", "power supply", "substation", "11 kv", "switchgear"],
    "water": ["water supply", "water network", "reservoir", "water and sanitation", "bulk water"],
}

def strip_html(raw_html):
    text = unescape(raw_html or "")
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def classify_utility(text):
    text_lower = text.lower()
    scores = {u: sum(1 for kw in kws if kw in text_lower) for u, kws in UTILITY_KEYWORDS.items()}
    if scores["water"] == 0 and scores["electricity"] == 0:
        return "unclear"
    return max(scores, key=scores.get)

def classify_notice_type(title, lead_text):
    combined = (title + " " + lead_text).lower()

    if "rescheduled" in combined or "postponed" in combined:
        return "rescheduled"

    # water quality / contamination events -- checked early since these are
    # rare and important, and shouldn't get swallowed by generic "scheduled" wording
    if ("contaminat" in combined or "sewer discharge" in combined
            or "water quality" in combined or "e. coli" in combined
            or "ecoli" in combined or "compromised" in combined
            or "health risk" in combined):
        return "water_quality_failure"

    if (re.search(r'(?<!un)planned', combined) or "scheduled for" in combined
            or "scheduled work" in combined or "maintenance" in combined
            or "bulk meter" in combined or "valve installation" in combined
            or "valve replacement" in combined or "upgrad" in combined
            or "tie-in" in combined or "tie in connection" in combined
            or "valve chamber" in combined or "t-piece" in combined
            or "prv" in combined or "pressure-reducing valve" in combined
            or "faulty equipment" in combined or "installation of" in combined):
        return "planned_maintenance"

    if ("system update" in combined or "water supply update" in combined
            or "steady recovery" in combined or "recovery period" in combined
            or "struggling to recover" in combined or "severe strain" in combined
            or "under strain" in combined or "high consumption" in combined
            or "critical level" in combined):
        return "system_status_update"

    if ("burst" in combined or "leak" in combined or "crack" in combined
            or "sinkhole" in combined or "vandal" in combined or "theft" in combined
            or "illegal connection" in combined or "pump failure" in combined
            or "power failure" in combined or "load shedding" in combined):
        return "unplanned_failure"

    return "unclassified"

def extract_areas(text):
    patterns = [
        r'following areas?(?: will be| are)? affected[:\-]?\s*(.+?)(?:\.|$)',
        r'affected areas?(?: include)?[:\-]?\s*(.+?)(?:\.|$)',
        r'falls? under[:\-]?\s*(.+?)(?:\.|$)',
    ]
    for p in patterns:
        match = re.search(p, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""

with open(INPUT_FILE, "r", encoding="utf-8") as f:
    posts = json.load(f)

rows = []
for post in posts:
    title = strip_html(post.get("title", {}).get("rendered", ""))
    content = strip_html(post.get("content", {}).get("rendered", ""))
    date = post.get("date", "")
    link = post.get("link", "") or post.get("guid", {}).get("rendered", "")

    lead_text = content[:350]
    utility = classify_utility(title + " " + lead_text)
    notice_type = classify_notice_type(title, lead_text)
    areas = extract_areas(content)

    rows.append({
        "incident_id": post.get("id", ""),
        "date": date,
        "date_confidence": "confirmed",
        "utility": utility,
        "notice_type": notice_type,
        "title": title,
        "affected_areas_raw": areas,
        "region_ward": "TBD",
        "asset_type": "TBD",
        "source_url": link,
        "notes": content[:500]
    })

fieldnames = ["incident_id", "date", "date_confidence", "utility", "notice_type",
              "title", "affected_areas_raw", "region_ward", "asset_type",
              "source_url", "notes"]

with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

print(f"Parsed {len(rows)} posts -> {OUTPUT_FILE}")

print("\nUtility breakdown:")
for u, c in Counter(r["utility"] for r in rows).most_common():
    print(f"  {u}: {c}")

water_rows = [r for r in rows if r["utility"] == "water"]
print(f"\nNotice type breakdown (water only, {len(water_rows)} posts):")
for n, c in Counter(r["notice_type"] for r in water_rows).most_common():
    print(f"  {n}: {c}")
