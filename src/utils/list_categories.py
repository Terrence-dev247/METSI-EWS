"""
Diagnostic script used once to discover the WordPress category IDs (58 =
Media Releases, 60 = Service Interruptions). Not part of regular pipeline
reruns -- kept for historical reference.
"""
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE = "https://www.tshwane.gov.za/index.php"
all_categories = []
page = 1

while True:
    resp = requests.get(
        BASE,
        params={
            "rest_route": "/wp/v2/categories",
            "per_page": 100,
            "page": page
        },
        verify=False,
        timeout=20
    )
    if resp.status_code != 200:
        break
    batch = resp.json()
    if not batch:
        break
    all_categories.extend(batch)
    page += 1

# sort by post count, descending -- the categories actually used a lot
all_categories.sort(key=lambda c: c.get("count", 0), reverse=True)

print(f"Total categories found: {len(all_categories)}\n")
print(f"{'ID':<6}{'Count':<8}Name")
print("-" * 50)
for c in all_categories:
    print(f"{c['id']:<6}{c['count']:<8}{c['name']}")