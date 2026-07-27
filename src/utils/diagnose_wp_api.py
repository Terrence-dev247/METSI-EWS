"""
Diagnostic script used once to find the correct WordPress REST API endpoint
format for tshwane.gov.za (pretty permalinks are disabled, so it needs the
?rest_route= fallback). Not part of regular pipeline reruns -- kept for
historical reference.
"""
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CANDIDATES = [
    "https://www.tshwane.gov.za/wp-json/",
    "https://tshwane.gov.za/wp-json/",
    "https://www.tshwane.gov.za/wp-json/wp/v2/posts",
    "https://www.tshwane.gov.za/index.php?rest_route=/wp/v2/posts&categories=60&per_page=5",
    "https://www.tshwane.gov.za/wp-json/wp/v2/categories?search=water",
]

for url in CANDIDATES:
    try:
        resp = requests.get(url, verify=False, timeout=15)
        content_type = resp.headers.get("Content-Type", "unknown")
        print(f"\nURL: {url}")
        print(f"  Status: {resp.status_code}")
        print(f"  Content-Type: {content_type}")
        print(f"  First 200 chars: {resp.text[:200]!r}")
    except Exception as e:
        print(f"\nURL: {url}")
        print(f"  ERROR: {e}")
