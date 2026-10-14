"""
Fetch real charging stations from Open Charge Map, then regenerate the seeds.

    set OCM_API_KEY=...              (Windows)   export OCM_API_KEY=...   (bash)
    pip install -r scripts/db/requirements.txt
    python scripts/db/fetch_stations.py

Get a free key at https://openchargemap.org (My Profile -> My Apps).
Writes the raw API responses to scripts/db/raw/ (commit them: the seeds are
generated from these files, so anyone can regenerate them without a key), then
runs generate_seeds.py.

  raw/ocm_city_<city>.json       stations within CITY_AREAS radius of each city
  raw/ocm_corridor_<id>.json     stations near each corridor waypoint

Data: Open Charge Map contributors, licensed CC BY 4.0
(https://openchargemap.org/site/about/terms). Keep the attribution in
database/README.md when using these files.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import generate_seeds
import seed_data as D

API = "https://api.openchargemap.io/v3/poi/"
CITY_MAX_RESULTS = 300
WAYPOINT_RADIUS_KM = 12  # waypoints are 20-60 km apart; overlap the circles
WAYPOINT_MAX_RESULTS = 100


def fetch(key: str, lat: float, lon: float, radius_km: float, max_results: int) -> list[dict]:
    params = {
        "output": "json",
        "countrycode": "IN",
        "latitude": lat,
        "longitude": lon,
        "distance": radius_km,
        "distanceunit": "KM",
        "maxresults": max_results,
        "compact": "true",  # reference data as IDs (ConnectionTypeID etc.), smaller payload
        "verbose": "false",
    }
    req = urllib.request.Request(
        API + "?" + urllib.parse.urlencode(params),
        headers={"X-API-Key": key, "User-Agent": "ev-charging-network-seed/1.0 (BACSE202 student project)"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def save(name: str, pois: list[dict]) -> None:
    generate_seeds.RAW.mkdir(parents=True, exist_ok=True)
    pois = sorted(pois, key=lambda p: p["ID"])  # stable file content between runs
    (generate_seeds.RAW / name).write_text(json.dumps(pois, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  raw/{name}: {len(pois)} POIs")


def main() -> None:
    key = os.environ.get("OCM_API_KEY", "").strip()
    if not key:
        sys.exit("OCM_API_KEY is not set. Get a free key at https://openchargemap.org (My Profile -> My Apps).")

    try:
        print("Cities")
        for city, (lat, lon, radius) in D.CITY_AREAS.items():
            save(f"ocm_city_{city}.json", fetch(key, lat, lon, radius, CITY_MAX_RESULTS))
            time.sleep(1)  # be polite to a free, volunteer-run API

        print("Corridors")
        for cor in D.CORRIDORS:
            found = {}
            for _, lat, lon, _ in cor["waypoints"]:
                for poi in fetch(key, lat, lon, WAYPOINT_RADIUS_KM, WAYPOINT_MAX_RESULTS):
                    found[poi["ID"]] = poi
                time.sleep(1)
            save(f"ocm_corridor_{cor['corridor_id']}.json", list(found.values()))
    except urllib.error.HTTPError as exc:
        sys.exit(f"Open Charge Map returned HTTP {exc.code}: check OCM_API_KEY. ({exc.reason})")
    except urllib.error.URLError as exc:
        sys.exit(f"Could not reach Open Charge Map: {exc.reason}")

    generate_seeds.main()


if __name__ == "__main__":
    main()
