"""Offline, provenance-preserving FishBase parquet → PostgreSQL ingestion."""

import argparse
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import duckdb
import psycopg
from psycopg.types.json import Jsonb

from app.config import Settings
from app.fishbase.snapshot import TABLES, download_snapshot, source_url

REQUIRED_COLUMNS = {
    "species": {
        "SpecCode",
        "Genus",
        "Species",
        "FBname",
        "DepthRangeShallow",
        "DepthRangeDeep",
        "Length",
        "LengthFemale",
        "LTypeMaxM",
        "LTypeMaxF",
        "BodyShapeI",
        "DemersPelag",
    },
    "ecology": {"autoctr", "SpecCode", "DietRemark", "FoodRemark", "FeedingType"},
    "morphdat": {"autoctr", "Speccode", "BodyShapeI", "BodyShapeII", "CShape"},
}


@dataclass
class Snapshot:
    release: str
    metadata: dict[str, dict]
    tables: dict[str, list[dict]]


@dataclass
class Publication:
    species: dict[str, Any]
    mapping: dict[str, Any]
    documents: list[dict[str, Any]]


def inspect_snapshot(path: Path) -> list[tuple]:
    if not path.is_file() or path.suffix != ".parquet":
        raise ValueError("Expected an existing local .parquet snapshot")
    with duckdb.connect() as connection:
        return connection.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(path)]).fetchall()


def load_snapshot(directory: Path, release: str) -> Snapshot:
    metadata, tables = {}, {}
    for table in TABLES:
        path = directory / f"{table}.parquet"
        meta = json.loads(path.with_suffix(".meta.json").read_text())
        if (
            meta["release"] != release
            or meta["table"] != table
            or meta["url"] != source_url(release, table)
        ):
            raise ValueError(f"{table}: snapshot provenance mismatch")
        if hashlib.sha256(path.read_bytes()).hexdigest() != meta["sha256"]:
            raise ValueError(f"{table}: snapshot checksum mismatch")
        if datetime.fromisoformat(meta["captured_at"]).tzinfo is None:
            raise ValueError(f"{table}: captured_at must include a timezone")
        with duckdb.connect() as db:
            columns = {row[0] for row in inspect_snapshot(path)}
            if missing := REQUIRED_COLUMNS[table] - columns:
                raise ValueError(f"{table}: missing columns {sorted(missing)}")
            # DuckDB serializes timestamps without discarding raw fields or reference IDs.
            values = db.execute("SELECT to_json(t) FROM read_parquet(?) t", [str(path)]).fetchall()
        tables[table] = [json.loads(row[0]) for row in values]
        if not tables[table]:
            raise ValueError(f"{table}: empty snapshot")
        metadata[table] = meta
    codes = [row["SpecCode"] for row in tables["species"]]
    if any(not isinstance(code, int) or code < 0 for code in codes) or len(set(codes)) != len(
        codes
    ):
        raise ValueError("species: SpecCode must be unique nonnegative integers")
    return Snapshot(release, metadata, tables)


def accepted_taxa(paths: list[Path]) -> dict[str, dict]:
    """Consume captured WoRMS JSON, not hand-written ID guesses or fuzzy matches."""
    taxa = {}
    for path in paths:
        records = json.loads(path.read_text())
        if isinstance(records, dict):
            records = [records]
        for row in records:
            aphia = row.get("AphiaID")
            if not (
                isinstance(aphia, int)
                and aphia > 0
                and row.get("valid_AphiaID") == aphia
                and row.get("status") == "accepted"
                and row.get("rank") == "Species"
                and row.get("isMarine") == 1
            ):
                continue
            name = row["scientificname"]
            if name in taxa and taxa[name]["AphiaID"] != aphia:
                raise ValueError(f"Ambiguous accepted WoRMS records for {name}")
            taxa[name] = row
    return taxa


def number(value: Any, *, positive: bool = False) -> float | None:
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value) if value >= 0 and (not positive or value > 0) else None


def text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def prepare_publications(snapshot: Snapshot, taxa: dict[str, dict]) -> list[Publication]:
    ecology, morphology = {}, {}
    for row in snapshot.tables["ecology"]:
        ecology.setdefault(row["SpecCode"], []).append(row)
    for row in snapshot.tables["morphdat"]:
        morphology.setdefault(row["Speccode"], []).append(row)
    publications = []
    used_aphia = set()
    for row in snapshot.tables["species"]:
        if row["SpecCode"] == 0:  # Upstream placeholder: preserve raw, never publish.
            continue
        name = f"{row['Genus']} {row['Species']}"
        taxon = taxa.get(name)
        if taxon is None:
            continue
        aphia, code = taxon["AphiaID"], row["SpecCode"]
        if aphia in used_aphia:
            raise ValueError(f"Multiple FishBase species map to AphiaID {aphia}")
        used_aphia.add(aphia)
        url = f"https://www.fishbase.se/summary/{code}"
        documents = []

        def document(field: str, value: str | None, *, documents=documents, aphia=aphia, url=url):
            if value:
                documents.append(
                    {
                        "id": uuid5(
                            NAMESPACE_URL, f"divepoint:fishbase:{snapshot.release}:{aphia}:{field}"
                        ),
                        "aphia_id": aphia,
                        "source": "fishbase",
                        "field": field,
                        "text": value,
                        "url": url,
                        "release_version": snapshot.release,
                    }
                )

        low, high = number(row["DepthRangeShallow"]), number(row["DepthRangeDeep"])
        if low is not None and high is not None and low > high:
            raise ValueError(f"{code}: inverted depth range")
        if low is not None:
            document("depth_min", f"Reported minimum depth: {low:g} m.")
        if high is not None:
            document("depth_max", f"Reported maximum depth: {high:g} m.")
        lengths = []
        for label, field, kind in [
            ("male/unsexed", "Length", "LTypeMaxM"),
            ("female", "LengthFemale", "LTypeMaxF"),
        ]:
            if (value := number(row[field], positive=True)) is not None:
                lengths.append(value)
                document(
                    field,
                    f"Reported maximum {label} length: {value:g} cm "
                    f"({text(row[kind]) or 'length type unspecified'}).",
                )
        document("habitat", text(row["DemersPelag"]))
        morphs = morphology.get(code, [])

        def unique_morph(field, morphs=morphs):
            values = {value for record in morphs if (value := text(record.get(field)))}
            return next(iter(values)) if len(values) == 1 else None

        # Conflicting morphology stays in raw storage; never choose an arbitrary sex/stock.
        body = text(row["BodyShapeI"]) or unique_morph("BodyShapeI")
        cross, tail = unique_morph("BodyShapeII"), unique_morph("CShape")
        for field, value in [("body_shape", body), ("cross_section", cross), ("tail_shape", tail)]:
            document(field, value)
        for record in ecology.get(code, []):
            for field in ["DietRemark", "FoodRemark", "FeedingType"]:
                document(f"ecology.{record['autoctr']}.{field}", text(record[field]))
        publications.append(
            Publication(
                species={
                    "aphia_id": aphia,
                    "scientific_name": taxon["scientificname"],
                    "common_names": [row["FBname"]] if text(row["FBname"]) else [],
                    "fishbase_spec_code": code,
                    "depth_min": low,
                    "depth_max": high,
                    "max_length_cm": max(lengths) if lengths else None,
                    "body_shape": body,
                    "cross_section": cross,
                    "tail_shape": tail,
                    "source_urls": {"fishbase": url},
                },
                mapping={
                    "release_version": snapshot.release,
                    "spec_code": code,
                    "aphia_id": aphia,
                    "fishbase_name": name,
                    "worms_record": taxon,
                },
                documents=documents,
            )
        )
    return publications


SPECIES_SQL = """
INSERT INTO species (aphia_id, scientific_name, common_names, fishbase_spec_code,
 depth_min, depth_max, max_length_cm, body_shape, cross_section, tail_shape, source_urls)
VALUES (%(aphia_id)s, %(scientific_name)s, %(common_names)s, %(fishbase_spec_code)s,
 %(depth_min)s, %(depth_max)s, %(max_length_cm)s, %(body_shape)s, %(cross_section)s,
 %(tail_shape)s, %(source_urls)s)
ON CONFLICT (aphia_id) DO UPDATE SET
 scientific_name = EXCLUDED.scientific_name,
 common_names = ARRAY(SELECT DISTINCT unnest(species.common_names || EXCLUDED.common_names)),
 fishbase_spec_code = EXCLUDED.fishbase_spec_code,
 depth_min = EXCLUDED.depth_min, depth_max = EXCLUDED.depth_max,
 max_length_cm = EXCLUDED.max_length_cm, body_shape = EXCLUDED.body_shape,
 cross_section = EXCLUDED.cross_section, tail_shape = EXCLUDED.tail_shape,
 source_urls = species.source_urls || EXCLUDED.source_urls
"""


def ingest(
    connection: psycopg.Connection, snapshot: Snapshot, publications: list[Publication]
) -> dict[str, Any]:
    """Stage a whole release and publish verified taxa in one transaction.

    Caller applies migrations first. An exception rolls back raw rows, facts and docs together.
    Re-import replaces the same release's raw rows and active FishBase facts idempotently.
    """
    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtext('divepoint:fishbase-ingest'))")
        for table, rows in snapshot.tables.items():
            meta = snapshot.metadata[table]
            cursor.execute(
                """INSERT INTO fishbase_snapshots
                (release_version, table_name, source_url, sha256, row_count, captured_at)
                VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (release_version,table_name)
                DO UPDATE SET source_url=EXCLUDED.source_url, sha256=EXCLUDED.sha256,
                row_count=EXCLUDED.row_count, captured_at=EXCLUDED.captured_at, imported_at=now()""",
                (
                    snapshot.release,
                    table,
                    meta["url"],
                    meta["sha256"],
                    len(rows),
                    meta["captured_at"],
                ),
            )
            cursor.execute(
                "DELETE FROM fishbase_records WHERE release_version=%s AND table_name=%s",
                (snapshot.release, table),
            )
            with cursor.copy(
                "COPY fishbase_records (release_version,table_name,row_number,spec_code,data) FROM STDIN"
            ) as copy:
                for index, row in enumerate(rows):
                    copy.write_row(
                        (
                            snapshot.release,
                            table,
                            index,
                            row.get("SpecCode", row.get("Speccode")),
                            Jsonb(row),
                        )
                    )
        for publication in publications:
            species = dict(publication.species)
            species["source_urls"] = Jsonb(species["source_urls"])
            cursor.execute(SPECIES_SQL, species)
            mapping = dict(publication.mapping)
            mapping["worms_record"] = Jsonb(mapping["worms_record"])
            cursor.execute(
                """INSERT INTO fishbase_taxon_mappings
                (release_version,spec_code,aphia_id,fishbase_name,worms_record)
                VALUES (%(release_version)s,%(spec_code)s,%(aphia_id)s,%(fishbase_name)s,%(worms_record)s)
                ON CONFLICT (release_version,spec_code) DO UPDATE SET
                aphia_id=EXCLUDED.aphia_id, fishbase_name=EXCLUDED.fishbase_name,
                worms_record=EXCLUDED.worms_record""",
                mapping,
            )
            # Clear obsolete text/embeddings from previous releases only for published taxa.
            cursor.execute(
                "DELETE FROM species_docs WHERE aphia_id=%s AND source='fishbase'",
                (species["aphia_id"],),
            )
            cursor.executemany(
                """INSERT INTO species_docs
                (id,aphia_id,source,field,text,url,release_version) VALUES
                (%(id)s,%(aphia_id)s,%(source)s,%(field)s,%(text)s,%(url)s,%(release_version)s)""",
                publication.documents,
            )
    return report(snapshot, publications)


def report(snapshot: Snapshot, publications: list[Publication]) -> dict[str, Any]:
    return {
        "release": snapshot.release,
        "raw_rows": {table: len(rows) for table, rows in snapshot.tables.items()},
        "published_species": len(publications),
        "unmapped_species": len(snapshot.tables["species"]) - len(publications),
        "documents": sum(len(item.documents) for item in publications),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-dir", type=Path, required=True)
    parser.add_argument("--release", required=True, help="Pinned release, e.g. v26.06")
    parser.add_argument(
        "--worms-json",
        type=Path,
        action="append",
        default=[],
        help="Captured accepted WoRMS records; repeat for multiple files",
    )
    parser.add_argument(
        "--download", action="store_true", help="Explicitly allow snapshot downloads"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Validate/prepare without a database"
    )
    args = parser.parse_args()
    settings = Settings()
    if args.download:
        download_snapshot(args.snapshot_dir, args.release, settings.user_agent)
    snapshot = load_snapshot(args.snapshot_dir, args.release)
    publications = prepare_publications(snapshot, accepted_taxa(args.worms_json))
    if args.dry_run:
        result = report(snapshot, publications)
    else:
        with psycopg.connect(settings.database_url) as connection:
            result = ingest(connection, snapshot, publications)
    print(json.dumps({"dry_run": args.dry_run, **result}, indent=2))


if __name__ == "__main__":
    main()
