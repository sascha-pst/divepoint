"""Capture checksum-verified Red Sea and Raja Ampat packs from public sources."""

import argparse
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import httpx

from app.checklist.manifest import accepted_taxon, build_species, qualify
from app.place.resolver import area_from_record

ROOT = Path(__file__).resolve().parents[1]
DESTINATIONS = {"red_sea": 4264, "raja_ampat": 21076}
FISHBASE = ROOT / "data/fishbase/v26.06/species.parquet"


def capture(pack):
    sources = []
    with httpx.Client(
        timeout=45,
        follow_redirects=True,
        transport=httpx.HTTPTransport(retries=2),
        headers={"User-Agent": "Divepoint/0.1 (verified offline dive capture)"},
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

        place = fetch(
            f"https://www.marineregions.org/rest/getGazetteerRecordByMRGID.json/{DESTINATIONS[pack]}/"
        )
        area = area_from_record(place)
        if not area or area["mrgid"] != DESTINATIONS[pack]:
            raise ValueError(f"Expected Marine Regions area for {pack}")
        occurrences = {}
        queries = [(0, 15, {}), (15, 30, {}), (30, 60, {})]
        if pack == "red_sea":
            # Include a regional dataset separately so abundant datasets cannot
            # crowd its records out of the bounded general sample.
            queries.append((0, 60, {"datasetid": "fbe20230-f4f1-48e7-83ee-4cd3ad15a1db"}))
        for low, high, extra in queries:
            payload = fetch(
                "https://api.obis.org/v3/occurrence",
                {
                    "geometry": area["geometry_wkt"],
                    "startdepth": low,
                    "enddepth": high,
                    "startdate": "1970-01-01",
                    "size": 5000 if pack == "red_sea" and not extra else 1000,
                    "taxonid": 293496,
                    "absence": "false",
                    "dropped": "false",
                    **extra,
                },
            )
            filtered = qualify(payload["results"], area, {"depth_m": [low, high], "months": []})
            occurrences.update((row["id"], row) for row in filtered)
            print(pack, low, high, len(filtered), "qualifying records", flush=True)

        rows = list(occurrences.values())
        candidates = dict.fromkeys(
            aphia_id
            for low, high in [(0, 15), (15, 30), (30, 60)]
            for aphia_id, _ in Counter(
                row["speciesid"] for row in rows if low <= float(row["depth"]) <= high
            ).most_common(24)
        )
        taxa = {}
        for aphia_id in candidates:
            payload = fetch(f"https://api.obis.org/v3/taxon/{aphia_id}")
            taxon = next(iter(payload["results"]), {})
            if accepted_taxon(taxon) and str(taxon["taxonID"]) == str(aphia_id):
                taxa[str(aphia_id)] = taxon

    names = [taxon["scientificName"] for taxon in taxa.values()]
    with duckdb.connect() as db:
        fishbase = [
            json.loads(row[0])
            for row in db.execute(
                "SELECT to_json(s) FROM read_parquet(?) s "
                "WHERE Genus || ' ' || Species IN (SELECT unnest(?)) ORDER BY SpecCode",
                [str(FISHBASE), names],
            ).fetchall()
        ]
    facts = {f"{row['Genus']} {row['Species']}": row for row in fishbase}
    filters = {"depth_m": [0, 30], "months": []}
    default_species = build_species(qualify(rows, area, filters), taxa, facts, filters)
    if not default_species:
        raise ValueError(f"{pack}: no verified species at 0–30 m")

    output = ROOT / "app/data" / pack
    output.mkdir(parents=True, exist_ok=True)
    assets = {
        "place": place,
        "occurrences": {"results": [row for row in rows if str(row["speciesid"]) in taxa]},
        "taxa": taxa,
        "fishbase": fishbase,
    }
    files = {}
    for name, data in assets.items():
        filename = f"{name}.json"
        contents = (json.dumps(data, separators=(",", ":")) + "\n").encode()
        (output / filename).write_bytes(contents)
        files[filename] = hashlib.sha256(contents).hexdigest()
    provenance = {
        "captured_at": datetime.now(UTC).isoformat(),
        "geometry_wkt": area["geometry_wkt"],
        "description": "Bounded sample of qualifying OBIS records, not abundance or a full checklist.",
        "sources": sources,
        "fishbase_release": "v26.06",
        "fishbase_parent_sha256": hashlib.sha256(FISHBASE.read_bytes()).hexdigest(),
        "files": files,
    }
    (output / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print(pack, len(default_species), "verified species at 0–30 m", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", choices=DESTINATIONS)
    capture(parser.parse_args().destination)
