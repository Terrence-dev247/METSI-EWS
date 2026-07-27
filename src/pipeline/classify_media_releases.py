import json
import csv
from html import unescape
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
INTERIM_DIR = PROJECT_ROOT / "data" / "interim"
INTERIM_DIR.mkdir(parents=True, exist_ok=True)

def strip_html(raw_html):
    text = unescape(raw_html or "")
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

NOISE_KEYWORDS = [
    "clinic", "fire station", "entrepreneurship", "diabetes", "embassy",
    "training", "audit", "payroll fraud", "imposter", "flea market",
    "world aids day", "early childhood", "air show", "expo", "freedom square",
    "showgrounds", "lease", "leasing", "tender award", "labour court",
    "arbitration", "public participation", "urban development framework",
    "stadium", "burglary", "amnesty period", "investigating unit",
    "blacklist", "misinformation", "rubbishes"
]

INCIDENT_KEYWORDS = [
    "emergency", "urgent", "unplanned", "vandalism", "vandal", "sabotage",
    "theft", "stolen", "power failure", "power trip", "power dip",
    "outbreak", "cholera", "leak", "burst", "thunderstorm", "sinkhole",
    "crack", "contaminat", "tamper"
]

PLANNED_KEYWORDS = [
    "planned", "scheduled", "postponement", "postponed", "rescheduled"
]

# Body text is far noisier than titles -- a post titled generically ("Water
# supply interruption affecting X") can still describe a genuine unplanned
# failure, OR can just be routine planned maintenance that happens to mention
# "leak"/"burst" as background ("to reduce non-revenue water leaks..."). So
# the body check below only fires on specific multi-word phrases that
# describe an event that has ALREADY happened and was NOT planned -- not on
# bare single keywords, which were too noisy in testing (~2/3 false-positive
# rate on loose keyword matching across the full media-releases archive).
STRONG_UNPLANNED_BODY_PHRASES = [
    "unforeseen interruption", "unforeseen", "unplanned",
    "major leak", "major crack", "significant leak", "continuous water leak",
    "burst water pipe", "burst pipe", "pipe burst",
    "discovered a major crack", "discovered a crack",
    "urgent repair", "emergency repair", "emergency shutdown",
    "compelled to drain", "had to shut down the water supply",
    # NOTE: deliberately NOT including bare "vandalism"/"vandal"/"sabotage"/
    # "tampering"/"theft" here -- tested against the real archive and they
    # fire on generic PSA language ("be vigilant against instances of
    # vandalism") as often as on actual events. Title-based INCIDENT_KEYWORDS
    # above already catches genuinely vandalism/sabotage-titled posts; for
    # ambiguous-titled posts it's not a reliable enough signal on its own.
]

# If any of these appear in the body, the post is planned/scheduled work --
# even if it also happens to mention a keyword above (e.g. "essential work,
# scheduled to last 8 hours, to reduce leaks on the network").
PLANNED_BODY_FRAMING_PHRASES = [
    "planned", "scheduled", "essential work", "will carry out",
    "tie-in connection", "upgrade work", "postponement", "postponed",
    "rescheduled", "installation of a", "connection to the water supply network",
]


def classify(title, content=""):
    t = title.lower()
    if any(kw in t for kw in NOISE_KEYWORDS):
        return "noise"
    if any(kw in t for kw in INCIDENT_KEYWORDS):
        return "incident_candidate"
    if any(kw in t for kw in PLANNED_KEYWORDS):
        return "planned_or_recovery"

    # Title was ambiguous -- the body is where the real signal often lives
    # for posts titled generically ("Water supply interruption affecting X").
    # NOTE: uses \b word-boundary matching, not plain substring -- "planned"
    # is a substring of "unplanned", so naive `in` matching here would block
    # the exact word meant to signal a genuine (un-)planned failure.
    c = content.lower()
    has_strong_unplanned = any(re.search(rf"\b{re.escape(p)}\b", c) for p in STRONG_UNPLANNED_BODY_PHRASES)
    has_planned_framing = any(re.search(rf"\b{re.escape(p)}\b", c) for p in PLANNED_BODY_FRAMING_PHRASES)
    if has_strong_unplanned and not has_planned_framing:
        return "incident_candidate"
    if any(kw in c for kw in PLANNED_KEYWORDS):
        return "planned_or_recovery"
    return "general_update"

all_posts = []
for fname in ["tshwane_media_releases_new_pre2024.json", "tshwane_media_releases_new_post2024.json"]:
    with open(INTERIM_DIR / fname, "r", encoding="utf-8") as f:
        all_posts.extend(json.load(f))

rows = []
for p in all_posts:
    title = strip_html(p["title"]["rendered"])
    content = strip_html(p["content"]["rendered"])
    label = classify(title, content)
    detected_via = "title" if any(kw in title.lower() for kw in INCIDENT_KEYWORDS) else "body"
    rows.append({
        "incident_id": p["id"],
        "date": p["date"],
        "title": title,
        "classification": label,
        "source_url": p.get("link", ""),
        "notes": content[:500],
        "_detected_via": detected_via,  # not written to CSV, console-only for review
    })

rows.sort(key=lambda r: r["date"])

from collections import Counter
print("Classification breakdown:")
for label, count in Counter(r["classification"] for r in rows).most_common():
    print(f"  {label}: {count}")

incident_candidates = [r for r in rows if r["classification"] == "incident_candidate"]
title_caught = [r for r in incident_candidates if r["_detected_via"] == "title"]
body_caught = [r for r in incident_candidates if r["_detected_via"] == "body"]

print(f"\n--- Incident candidates ({len(incident_candidates)}), chronological ---")
print(f"    ({len(title_caught)} caught by title keywords, {len(body_caught)} caught by body text only -- review these extra closely)")
for r in incident_candidates:
    flag = " [BODY-DETECTED -- title alone wouldn't have caught this]" if r["_detected_via"] == "body" else ""
    print(f"  [{r['date'][:10]}] {r['title']}{flag}")

# Strip the console-only field before writing
for r in incident_candidates:
    r.pop("_detected_via", None)

with open(INTERIM_DIR / "tshwane_incident_candidates.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=["incident_id", "date", "title", "classification", "source_url", "notes"])
    writer.writeheader()
    writer.writerows(incident_candidates)

print(f"\nSaved {len(incident_candidates)} incident candidates -> {INTERIM_DIR / 'tshwane_incident_candidates.csv'}")
