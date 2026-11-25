"""Capture an occurrence-backed Monterey starter pack (explicit live maintenance)."""

import hashlib
import json
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import httpx

ROOT = Path(__file__).parents[1]
OUTPUT = ROOT / "app/data/monterey"
AREA = "POLYGON((-122.12 36.57,-121.74 36.57,-121.74 37.02,-122.12 37.02,-122.12 36.57))"


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    sources = []
    with httpx.Client(
        timeout=45,
        follow_redirects=True,
        headers={"User-Agent": "Divepoint/0.1 (development verified dive capture)"},
    ) as client:

        def fetch(url, params=None):
            response = client.get(url, params=params)
            response.raise_for_status()
            sources.append(
                {
                    "url": str(response.url),
                    "captured_at": datetime.now(UTC).isoformat(),
                    "sha256": hashlib.sha256(response.content).hexdigest(),
                }
            )
            return response.json()

        place = fetch("https://www.marineregions.org/rest/getGazetteerRecordByMRGID.json/19167/")
        occurrences = fetch(
            "https://api.obis.org/v3/occurrence",
            {
                "geometry": AREA,
                "startdepth": 0,
                "enddepth": 60,
                "startdate": "1970-01-01",
                "size": 1000,
                "taxonid": 293496,
                "absence": "false",
                "dropped": "false",
            },
        )
        (OUTPUT / "place.json").write_text(json.dumps(place, indent=2) + "\n")
        (OUTPUT / "occurrences.json").write_text(
            json.dumps(occurrences, separators=(",", ":")) + "\n"
        )
        counts = Counter(
            row["speciesid"]
            for row in occurrences["results"]
            if row.get("speciesid")
            and row.get("marine") is True
            and row.get("flags") == []
            and row.get("bathymetry", 1) < 0
            and row.get("depth") is not None
            and 0 <= row["depth"] <= 30
            and row.get("date_year", 0) >= 1970
        )
        ids = [key for key, _ in counts.most_common(23)]
        if 274772 not in ids:
            ids.append(274772)
        taxa, photos = {}, {}
        for aphia in ids:
            try:
                records = fetch(f"https://api.obis.org/v3/taxon/{aphia}")
                taxon = records["results"][0]
                taxa[str(aphia)] = taxon
                photo = fetch(
                    "https://api.inaturalist.org/v1/taxa",
                    {"q": taxon["scientificName"], "rank": "species", "per_page": 5},
                )
                photos[str(aphia)] = {
                    "results": [
                        {
                            "name": match["name"],
                            "rank": match["rank"],
                            "default_photo": {"id": match["default_photo"]["id"]},
                        }
                        for match in photo.get("results", [])
                        if match.get("name") == taxon["scientificName"]
                        and match.get("rank") == "species"
                        and type((match.get("default_photo") or {}).get("id")) is int
                    ]
                }
                print(aphia, taxon["scientificName"], flush=True)
            except (httpx.HTTPError, IndexError, KeyError) as error:
                print("capture failed", aphia, str(error), flush=True)
            time.sleep(1)
        (OUTPUT / "taxa.json").write_text(json.dumps(taxa, indent=2) + "\n")
        (OUTPUT / "photos.json").write_text(json.dumps(photos, indent=2) + "\n")
    names = [taxon["scientificName"] for taxon in taxa.values()]
    snapshot = ROOT / "data/fishbase/v26.06/species.parquet"
    with duckdb.connect() as db:
        rows = db.execute(
            "SELECT to_json(s) FROM read_parquet(?) s WHERE Genus || ' ' || Species IN (SELECT unnest(?))",
            [str(snapshot), names],
        ).fetchall()
    fishbase = [json.loads(row[0]) for row in rows]
    (OUTPUT / "fishbase.json").write_text(json.dumps(fishbase, indent=2) + "\n")
    metadata = {
        "captured_at": datetime.now(UTC).isoformat(),
        "geometry_wkt": AREA,
        "description": "Bounded occurrence sample, not an exhaustive checklist or abundance estimate.",
        "sources": sources,
        "fishbase_release": "v26.06",
        "fishbase_parent_sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(),
    }
    metadata["files"] = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in OUTPUT.glob("*.json")
        if path.name != "provenance.json"
    }
    (OUTPUT / "provenance.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"Saved {len(taxa)} taxa, {len(fishbase)} FishBase rows.", flush=True)


if __name__ == "__main__":
    main()
