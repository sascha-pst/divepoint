"""Real PostgreSQL checks. Install the optional integration dependency group to run."""

import copy
from pathlib import Path

import psycopg
import pytest

from app.fishbase.loader import accepted_taxa, ingest, load_snapshot, prepare_publications

embedded_postgres = pytest.importorskip("embedded_postgres")
ROOT = Path(__file__).parents[3]
RECORDED = Path(__file__).parents[1] / "fixtures/recorded"


@pytest.fixture
def connection(tmp_path):
    with (
        embedded_postgres.get_server(tmp_path / "postgres") as server,
        psycopg.connect(server.get_uri(), autocommit=True) as connection,
    ):
        # Use the actual species/doc DDL; PostGIS is unrelated to this importer.
        connection.execute("CREATE EXTENSION vector")
        for statement in (ROOT / "database/001_initial.sql").read_text().split(";"):
            if statement.strip().startswith(
                ("CREATE TABLE species (", "CREATE TABLE species_docs (")
            ):
                connection.execute(statement)
        connection.execute((ROOT / "database/002_fishbase_ingestion.sql").read_text())
        yield connection


def test_import_reimport_and_rollback(connection):
    snapshot = load_snapshot(RECORDED / "fishbase/v26.06", "v26.06")
    taxa = accepted_taxa([RECORDED / "worms.json"])
    publications = prepare_publications(snapshot, taxa)
    result = ingest(connection, snapshot, publications)
    assert result["published_species"] == 1
    assert connection.execute("SELECT count(*) FROM fishbase_records").fetchone()[0] == 19
    assert connection.execute(
        "SELECT depth_min,depth_max,max_length_cm FROM species"
    ).fetchone() == (9, 46, 42)
    document_count = connection.execute("SELECT count(*) FROM species_docs").fetchone()[0]
    ids = connection.execute("SELECT id FROM species_docs ORDER BY id").fetchall()
    # Preserve independently supplied data on upsert.
    connection.execute(
        "UPDATE species SET iucn_status='LC', source_urls=source_urls || '{\"other\":\"https://example.test\"}'::jsonb"
    )
    ingest(connection, snapshot, publications)
    assert connection.execute("SELECT count(*) FROM fishbase_records").fetchone()[0] == 19
    assert connection.execute("SELECT id FROM species_docs ORDER BY id").fetchall() == ids
    assert connection.execute(
        "SELECT iucn_status,source_urls->>'other' FROM species"
    ).fetchone() == ("LC", "https://example.test")
    # Force a database error after raw COPY and species upsert, verifying atomic rollback.
    broken = copy.deepcopy(publications)
    broken[0].documents[0]["text"] = None
    changed = copy.deepcopy(snapshot)
    changed.tables["ecology"].append(dict(changed.tables["ecology"][0]))
    with pytest.raises(psycopg.errors.NotNullViolation):
        ingest(connection, changed, broken)
    assert connection.execute("SELECT count(*) FROM fishbase_records").fetchone()[0] == 19
    assert connection.execute("SELECT count(*) FROM species_docs").fetchone()[0] == document_count
    assert (
        connection.execute(
            "SELECT row_count FROM fishbase_snapshots WHERE table_name='ecology'"
        ).fetchone()[0]
        == 6
    )
