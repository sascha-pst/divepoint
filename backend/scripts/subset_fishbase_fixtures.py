"""Derive small offline parquet fixtures from a downloaded, pinned real snapshot.

Run from the repository root with PYTHONPATH=backend. No network calls are made.
"""

import argparse
import hashlib
import json
from pathlib import Path

import duckdb

from app.fishbase.loader import load_snapshot
from app.fishbase.snapshot import TABLES


def subset(source: Path, output: Path, release: str):
    snapshot = load_snapshot(source, release)
    output.mkdir(parents=True, exist_ok=True)
    with duckdb.connect() as db:
        for table in TABLES:
            column = "Speccode" if table == "morphdat" else "SpecCode"
            predicate = f"{column} IN (2,3,3950)"
            target = output / f"{table}.parquet"
            db.read_parquet(str(source / target.name)).filter(predicate).write_parquet(str(target))
            metadata = dict(snapshot.metadata[table])
            metadata.update(
                parent_sha256=metadata["sha256"],
                sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                bytes=target.stat().st_size,
                subset_predicate=predicate,
            )
            target.with_suffix(".meta.json").write_text(json.dumps(metadata, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--release", required=True)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error("Fixture output must differ from source snapshot directory")
    subset(args.source, args.output, args.release)
