"""Only individually qualifying occurrences can enter a manifest."""

import math
from collections import defaultdict
from datetime import UTC, datetime


def finite(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (ValueError, TypeError):
        return None


def qualify(records: list[dict], place: dict, filters: dict, earliest_year=1970) -> list[dict]:
    west, south, east, north = place["bounds"]
    low, high = filters["depth_m"]
    accepted, seen = [], set()
    for row in records:
        lon, lat, depth, bottom = (
            finite(row.get(field))
            for field in ["decimalLongitude", "decimalLatitude", "depth", "bathymetry"]
        )
        if None in (lon, lat, depth, bottom):
            continue
        if not (
            west <= lon <= east and south <= lat <= north and low <= depth <= high and bottom < 0
        ):
            continue
        # Missing QC status is unknown, not a clean record. This intentionally favors precision.
        if (
            row.get("marine") is not True
            or row.get("flags") != []
            or row.get("dropped") is not False
        ):
            continue
        if (
            row.get("absence") is not False
            or str(row.get("occurrenceStatus", "")).lower() != "present"
        ):
            continue
        if str(row.get("speciesid")) != str(row.get("aphiaID")):
            continue  # No genus-level records or inferred species from parent taxonomy.
        try:
            aphia = int(row["speciesid"])
            start = datetime.fromtimestamp(float(row["date_start"]) / 1000, UTC)
            end = datetime.fromtimestamp(float(row["date_end"]) / 1000, UTC)
        except (KeyError, ValueError, TypeError, OSError, OverflowError):
            continue
        if aphia <= 0 or start.year < earliest_year or end > datetime.now(UTC) or end < start:
            continue
        if filters["months"] and (
            start.year != end.year
            or start.month != end.month
            or start.month not in filters["months"]
        ):
            continue  # Never infer a month from an ambiguous date interval.
        record_id = row.get("id")
        if not record_id or record_id in seen:
            continue
        seen.add(record_id)
        accepted.append(row)
    return accepted


def accepted_taxon(taxon: dict) -> bool:
    return (
        taxon.get("taxonRank") == "Species"
        and taxon.get("taxonomicStatus") == "accepted"
        and taxon.get("taxonID") == taxon.get("acceptedNameUsageID")
        and taxon.get("is_marine") is True
        and taxon.get("is_terrestrial") is not True
    )


def build_species(
    records: list[dict], taxa: dict[str, dict], fishbase: dict[str, dict], filters: dict
) -> list[dict]:
    grouped = defaultdict(list)
    for record in records:
        grouped[str(record["speciesid"])].append(record)
    species = []
    for key, rows in grouped.items():
        taxon = taxa.get(key)
        if not taxon or str(taxon.get("taxonID")) != key or not accepted_taxon(taxon):
            continue
        fact = fishbase.get(taxon["scientificName"], {})
        depths = [float(row["depth"]) for row in rows]
        fact_low, fact_high = (
            finite(fact.get("DepthRangeShallow")),
            finite(fact.get("DepthRangeDeep")),
        )
        depths = [
            d
            for d in depths
            if (fact_low is None or d >= fact_low) and (fact_high is None or d <= fact_high)
        ]
        if not depths:
            continue
        rows = [row for row in rows if float(row["depth"]) in depths]
        common = fact.get("FBname") or next(iter(taxon.get("vernacularNames") or []), None)
        mean = sum(depths) / len(depths)
        species.append(
            {
                "aphia_id": int(key),
                "name": taxon["scientificName"],
                "common": common or taxon["scientificName"],
                "family": taxon.get("family", "Unknown"),
                "body_shape": fact.get("BodyShapeI"),
                "zone": "surface" if mean <= 5 else "reef" if mean <= 30 else "wall",
                "depth_m": [min(depths), max(depths)],
                "weight": math.log1p(len(rows)),
                "evidence": {
                    "obis_records": len(rows),
                    "gbif_records": 0,
                    "latest_year": max(
                        datetime.fromtimestamp(float(row["date_start"]) / 1000, UTC).year
                        for row in rows
                    ),
                    "record_urls": [f"https://obis.org/occurrence/{row['id']}" for row in rows[:3]],
                    "source_url": f"https://obis.org/taxon/{key}",
                    "dataset_urls": sorted(
                        {
                            f"https://obis.org/dataset/{row['dataset_id']}"
                            for row in rows
                            if row.get("dataset_id")
                        }
                    ),
                    "scope": "validated records in a bounded sample; not total abundance",
                },
            }
        )
    species.sort(key=lambda s: (-s["weight"], s["aphia_id"]))
    for index, item in enumerate(species):
        percentile = index / len(species)
        item["rarity"] = (
            "common"
            if percentile < 0.5
            else "uncommon"
            if percentile < 0.8
            else "rare"
            if percentile < 0.95
            else "legendary"
        )
    return species
