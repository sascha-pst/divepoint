"""Explicit live maintenance command; never called by tests."""

import argparse
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

AREA = "POLYGON((-121.95 36.55,-121.85 36.55,-121.85 36.65,-121.95 36.65,-121.95 36.55))"
REQUESTS = {
    "marineregions": (
        "https://www.marineregions.org/rest/getGazetteerRecordsByName.json/Monterey%20Bay/",
        {"like": "true", "fuzzy": "true"},
    ),
    "obis": (
        "https://api.obis.org/v3/checklist",
        {"geometry": AREA, "startdepth": 0, "enddepth": 30, "startdate": "1970-01-01"},
    ),
    "gbif": (
        "https://api.gbif.org/v1/occurrence/search",
        {
            "geometry": AREA,
            "facet": "speciesKey",
            "facetLimit": 1000,
            "limit": 0,
            "hasCoordinate": "true",
            "hasGeospatialIssue": "false",
            "occurrenceStatus": "PRESENT",
            "year": "1970,2100",
        },
    ),
    "worms": (
        "https://www.marinespecies.org/rest/AphiaRecordsByName/Sebastes%20atrovirens",
        {"marine_only": "true", "like": "false"},
    ),
    "inat": (
        "https://api.inaturalist.org/v1/taxa",
        {"q": "Sebastes atrovirens", "rank": "species", "per_page": 1},
    ),
    "worms_taxon": ("https://www.marinespecies.org/rest/AphiaRecordByAphiaID/274772", {}),
    "inat_taxon": ("https://api.inaturalist.org/v1/taxa/64481", {}),
}


def capture(output: Path, user_agent: str, sources: list[str] | None = None):
    output.mkdir(parents=True, exist_ok=True)
    failures = []
    with httpx.Client(
        timeout=45,
        headers={"User-Agent": user_agent, "Accept": "application/json"},
        follow_redirects=True,
    ) as client:
        for name, (url, params) in REQUESTS.items():
            if sources and name not in sources:
                continue
            try:
                response = client.get(url, params=params)
                response.raise_for_status()
                response.json()  # Never record an HTML error page as a fixture.
                body = response.content
                (output / f"{name}.json").write_bytes(body)
                metadata = {
                    "captured_at": datetime.now(UTC).isoformat(),
                    "url": str(response.url),
                    "status": response.status_code,
                    "sha256": hashlib.sha256(body).hexdigest(),
                    "headers": {
                        k: v
                        for k, v in response.headers.items()
                        if k in {"content-type", "etag", "last-modified", "date"}
                    },
                    "user_agent": user_agent,
                    "kind": "recorded upstream response",
                }
                (output / f"{name}.meta.json").write_text(json.dumps(metadata, indent=2) + "\n")
                print(f"{name}: {len(body)} bytes", flush=True)
            except (httpx.HTTPError, ValueError) as error:
                failures.append(name)
                print(f"{name}: FAILED {error}", flush=True)
            time.sleep(1)
    if failures:
        raise SystemExit("Failed sources: " + ", ".join(failures))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path(__file__).parents[1] / "tests/fixtures/recorded"
    )
    parser.add_argument(
        "--user-agent", default="Divepoint/0.1 (development biodiversity API fixture capture)"
    )
    parser.add_argument(
        "--source",
        action="append",
        choices=sorted(REQUESTS),
        help="Capture only these sources; repeat as needed",
    )
    args = parser.parse_args()
    capture(args.output, args.user_agent, args.source)
