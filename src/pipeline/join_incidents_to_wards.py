"""
Tags incidents with their Tshwane ward (WardID / WardLabel) via point-in-polygon
spatial join against the MDB Wards 2020 shapefile.

WHY THIS APPROACH:
The ward shapefile has no suburb-name column to match against - it's pure
polygon geometry. So "ward TBD" rows can't be fixed by string-matching;
each incident needs a lat/lon point, and that point gets dropped onto the
ward polygons to see which one it falls inside.

REQUIREMENTS (run locally, or upload tshwane_wards_2020.geojson into this
environment and re-run here):
    pip install geopandas shapely --break-system-packages

INPUTS:
    - tshwane_water_incidents_batch1.csv   (must have lat, lon columns - already added)
    - tshwane_wards_2020.geojson           (WardID 799000XX, WardLabel TSH_1..TSH_107)

OUTPUT:
    - tshwane_water_incidents_batch1_wardtagged.csv

NOTE: this script is intentionally parametrized and re-run by hand for each
new incident batch -- just edit INCIDENTS_CSV / OUT_CSV below before running.
"""
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
INTERIM_DIR = PROJECT_ROOT / "data" / "interim"

# EDIT THESE TWO PER BATCH:
INCIDENTS_CSV = INTERIM_DIR / "tshwane_incident_candidates_final_geocoded.csv"
OUT_CSV = INTERIM_DIR / "tshwane_incident_candidates_final_wardtagged.csv"

WARDS_GEOJSON = RAW_DIR / "tshwane_wards_2020.geojson"

incidents = pd.read_csv(INCIDENTS_CSV)
wards = gpd.read_file(WARDS_GEOJSON)

# wards file is already EPSG:4326 per the project notes - confirm, reproject if not
if wards.crs is None or wards.crs.to_epsg() != 4326:
    wards = wards.to_crs(epsg=4326)

# build point geometries from incident lat/lon (rows with missing coords are skipped)
geocoded = incidents.dropna(subset=["lat", "lon"]).copy()
geocoded["geometry"] = geocoded.apply(lambda r: Point(r["lon"], r["lat"]), axis=1)
gdf_incidents = gpd.GeoDataFrame(geocoded, geometry="geometry", crs="EPSG:4326")

# point-in-polygon join; keep WardID/WardLabel from the ward layer
joined = gpd.sjoin(gdf_incidents, wards[["WardID", "WardLabel", "geometry"]],
                    how="left", predicate="within")

# merge ward tags back onto the full incident table (including any rows with no coords)
result = incidents.merge(
    joined[["incident_id", "WardID", "WardLabel"]],
    on="incident_id", how="left"
)

unmatched = result[result["WardLabel"].isna() & result["lat"].notna()]
if len(unmatched):
    print(f"WARNING: {len(unmatched)} geocoded incident(s) fell outside all ward "
          f"polygons (likely just outside the metro boundary or a geocoding miss):")
    print(unmatched[["incident_id", "primary_area", "lat", "lon"]].to_string(index=False))

result.to_csv(OUT_CSV, index=False)
print(f"\nWrote {OUT_CSV} - {result['WardLabel'].notna().sum()}/{len(result)} incidents now ward-tagged")
