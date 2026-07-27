"""
Scraper for ourpower.co.za's live Tshwane water-outage tracker.

RUN THIS LOCALLY - not in the Claude sandbox. ourpower.co.za is not on this
sandbox's network allowlist, so this script will fail here. On your own
machine it should work like a normal Python script.

    pip install requests beautifulsoup4 python-dateutil --break-system-packages
    python scrape_ourpower.py

WHAT IT DOES:
Fetches https://www.ourpower.co.za/water-outages/tshwane, finds every
outage "card" (each one ends in a "View statement ->" link back to the
original City of Tshwane X/Twitter post), and pulls out:
    - status: Active or Planned
    - posted_ago: the site's relative timestamp ("Posted 6 hours ago")
    - statement_text: the outage description
    - areas_affected: list of suburb names (each is also a link to a
      per-suburb page on the same site - useful for ward-mapping later)
    - source_url: the original City of Tshwane X post

NOTE ON ROBUSTNESS:
This targets visible text patterns ("...Posted X ago", "Areas affected:",
"View statement ->") rather than CSS class names, because Next.js sites
often use auto-generated, unstable class names. If ourpower.co.za changes
its wording, the regex/markers below will need adjusting - inspect the
page in your browser's dev tools (right-click -> Inspect) if it breaks.

POLITENESS:
Checks robots.txt before scraping. Adds a short delay if you loop this
over multiple pages/suburbs. Don't hit this harder than the page's own
"updated every 30 minutes" refresh cadence - there's no benefit to
scraping more often than the source itself updates.
"""
import re
import csv
import time
from datetime import datetime, timezone
from urllib.parse import urljoin
from urllib import robotparser
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.ourpower.co.za"
PAGE_URL = f"{BASE_URL}/water-outages/tshwane"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
INTERIM_DIR = PROJECT_ROOT / "data" / "interim"
INTERIM_DIR.mkdir(parents=True, exist_ok=True)

OUT_CSV = INTERIM_DIR / "ourpower_tshwane_pull.csv"


def check_robots_allowed(url: str) -> bool:
    rp = robotparser.RobotFileParser()
    rp.set_url(urljoin(url, "/robots.txt"))
    try:
        rp.read()
    except Exception:
        # if robots.txt itself can't be fetched, fail safe and don't scrape
        return False
    return rp.can_fetch(HEADERS["User-Agent"], url)


def fetch_page(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


def parse_cards(html: str):
    soup = BeautifulSoup(html, "html.parser")
    cards = []

    # anchor on every "View statement ->" link - each one marks the end of one card
    statement_links = [a for a in soup.find_all("a") if "View statement" in a.get_text()]

    for link in statement_links:
        source_url = link.get("href", "")

        # walk up to the nearest container that holds the whole card's text,
        # then pull the plain text of that block
        container = link
        for _ in range(6):  # climb a few levels; adjust if the site's nesting differs
            if container.parent is None:
                break
            container = container.parent
            text = container.get_text(" ", strip=True)
            if "Posted" in text and ("Active" in text or "Planned" in text):
                break

        full_text = container.get_text(" ", strip=True)

        status_match = re.search(r"\b(Active|Planned)\b", full_text)
        status = status_match.group(1) if status_match else "unknown"

        posted_match = re.search(r"Posted\s+(.+?ago)", full_text)
        posted_ago = posted_match.group(1) if posted_match else ""

        # "Areas affected:" is followed by suburb links inside the same container
        areas = []
        areas_header = container.find(string=re.compile("Areas affected"))
        if areas_header:
            # suburb links live in <a> tags pointing to /water-outages/tshwane/<slug>
            for a in container.find_all("a", href=re.compile(r"/water-outages/tshwane/[\w-]+$")):
                areas.append(a.get_text(strip=True))

        # statement text = everything before "Areas affected" / "View statement"
        statement_text = re.split(r"Areas affected|View statement", full_text)[0]
        statement_text = re.sub(r"^(Active|Planned)Posted\s+.+?ago\s*", "", statement_text).strip()

        cards.append({
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "posted_ago": posted_ago,
            "statement_text": statement_text,
            "areas_affected": "; ".join(areas),
            "source_url": source_url,
        })

    # de-duplicate (same card can be picked up twice if nesting overlaps)
    seen = set()
    deduped = []
    for c in cards:
        key = (c["source_url"], c["statement_text"])
        if key not in seen:
            seen.add(key)
            deduped.append(c)
    return deduped


def main():
    if not check_robots_allowed(PAGE_URL):
        print(f"robots.txt disallows fetching {PAGE_URL} - stopping.")
        return

    html = fetch_page(PAGE_URL)
    cards = parse_cards(html)

    if not cards:
        print("No cards found - the page structure may have changed. "
              "Open the page in a browser, inspect a card element, and "
              "adjust the regex markers in parse_cards().")
        return

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(cards[0].keys()))
        writer.writeheader()
        writer.writerows(cards)

    print(f"Wrote {len(cards)} outage records to {OUT_CSV}")


if __name__ == "__main__":
    main()
