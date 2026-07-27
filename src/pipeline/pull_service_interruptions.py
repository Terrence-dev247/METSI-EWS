import requests
import json
import time
import urllib3
from datetime import datetime
from pathlib import Path

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Renamed from check_wp_api.py — this is the real cat=60 puller, not a diagnostic.
# Lives in <project_root>/src/pipeline/ — output goes to <project_root>/data/raw/
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

BASE = "https://www.tshwane.gov.za/index.php"
CATEGORY_ID = 60  # "Service Interruptions"
OUTPUT_FILE = RAW_DIR / "tshwane_service_interruptions_raw.json"


def archive_and_diff(output_file, new_posts):
    """Compare against the existing file before overwriting. If the fresh pull is
    missing anything that was there before (removed/recategorized on the City's
    site, or just an API hiccup), archive the old file with a timestamp instead
    of silently losing it."""
    if not output_file.exists():
        return
    with open(output_file, "r", encoding="utf-8") as f:
        old_posts = json.load(f)
    old_ids = {p["id"] for p in old_posts}
    new_ids = {p["id"] for p in new_posts}
    added = new_ids - old_ids
    removed = old_ids - new_ids

    if added:
        print(f"\n+{len(added)} new post(s) since last pull.")
    if removed:
        removed_posts = [p for p in old_posts if p["id"] in removed]
        print(f"\n⚠ {len(removed)} post(s) in the existing file are NOT in this fresh pull "
              "(removed/recategorized on the City's site, or an API hiccup):")
        for p in removed_posts:
            print(f"    id {p['id']} | {p['date'][:10]} | {p['title']['rendered']}")
        backup_path = output_file.with_name(
            f"{output_file.stem}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}{output_file.suffix}"
        )
        output_file.rename(backup_path)
        print(f"Archived the previous file to {backup_path} before overwriting — nothing is lost.")
    if not added and not removed:
        print("\nNo change vs. the existing file — identical set of posts.")


all_posts = []
page = 1

while True:
    try:
        resp = requests.get(
            BASE,
            params={
                "rest_route": "/wp/v2/posts",
                "categories": CATEGORY_ID,
                "per_page": 100,
                "page": page
            },
            verify=False,
            timeout=20
        )

        if resp.status_code != 200:
            print(f"Stopped at page {page}: HTTP {resp.status_code}")
            break

        batch = resp.json()

        if not batch:
            print(f"Page {page} empty -- reached the end.")
            break

        all_posts.extend(batch)
        print(f"page {page}: {len(batch)} posts, total so far {len(all_posts)}")

        page += 1
        time.sleep(1)  # be polite to their server

    except Exception as e:
        print("ERROR:", e)
        break

print(f"\nTotal posts pulled: {len(all_posts)}")

if all_posts:
    archive_and_diff(OUTPUT_FILE, all_posts)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_posts, f, ensure_ascii=False, indent=2)
    print(f"Saved raw data to {OUTPUT_FILE}")

    # quick peek at date range covered
    dates = sorted(p["date"] for p in all_posts)
    print(f"Earliest post: {dates[0]}")
    print(f"Latest post:   {dates[-1]}")
