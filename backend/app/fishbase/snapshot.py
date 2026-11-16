"""Explicit downloads of pinned FishBase releases; no network use during import/tests."""

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import httpx

TABLES = ("species", "ecology", "morphdat")


def source_url(release: str, table: str) -> str:
    if not re.fullmatch(r"v\d{2}\.\d{2}", release) or table not in TABLES:
        raise ValueError("Expected a pinned vYY.MM FishBase release and supported table")
    return f"https://data.source.coop/cboettig/fishbase/fb/{release}/parquet/{table}.parquet"


def download_snapshot(directory: Path, release: str, user_agent: str) -> None:
    # Validate each download before replacing its local parquet file.
    directory.mkdir(parents=True, exist_ok=True)
    with httpx.Client(
        timeout=120, follow_redirects=True, headers={"User-Agent": user_agent}
    ) as client:
        for table in TABLES:
            url = source_url(release, table)
            response = client.get(url)
            response.raise_for_status()
            body = response.content
            if not (body.startswith(b"PAR1") and body.endswith(b"PAR1")):
                raise ValueError(f"{table}: response is not a parquet file")
            temporary = directory / f"{table}.parquet.part"
            temporary.write_bytes(body)
            metadata = {
                "url": url,
                "sha256": hashlib.sha256(body).hexdigest(),
                "captured_at": datetime.now(UTC).isoformat(),
                "release": release,
                "table": table,
                "bytes": len(body),
            }
            temporary.replace(directory / f"{table}.parquet")
            (directory / f"{table}.meta.json").write_text(json.dumps(metadata, indent=2) + "\n")
