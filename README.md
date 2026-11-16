# Divepoint

Describe a marine place, explore species recorded there, and collect discoveries in a Fishdex.
See the [PRD](docs/PRD%20%E2%80%94%20Divepoint%20Describe%20a%20Place,%20Dive%20It,%20Meet%20What%20Lives%20There.md).

## Development

Requires Python 3.12+, uv, and Node 22+ (or Docker Compose).

```sh
uv sync --project backend
uv run --project backend uvicorn app.main:app --app-dir backend --reload
# In a second terminal:
cd game
npm install
npm run dev
```

API: http://localhost:8000/docs · client: http://localhost:5173

```sh
uv run --project backend pytest backend/tests
uv run --project backend python evals/run_evals.py --quick
cd game
npm run build
```

`docker compose up --build` starts Postgres 16 with PostGIS and pgvector, the API,
and the client. The SQL initializer runs only on a new database volume.
Copy `.env.example` to `.env` for local overrides. Configure a project contact
in the User-Agent before making live requests. No API keys are needed for M1.

## Current scope

M1 foundations: server-side provider adapters, timeout/retry/pacing, a process-local
30-day TTL cache, initial SQL schema, pinned FishBase parquet ingestion, offline tests,
and a TypeScript/Vite workspace with Phaser installed for M4. `/health` works;
all product routes return 501. No dive, occurrence evidence, or species facts are fabricated.

Fixtures include dated **real API responses** from all five providers and real FishBase
parquet subsets alongside synthetic edge cases. Every recorded body has checksum/provenance metadata.
Aggregate responses are discovery data, not evidence qualifying species for a dive.
Provider responses currently retain upstream JSON except typed WoRMS records and photo output.
The cache is volatile and has no eviction bound; use persistent bounded caching before production.
FishBase ingestion stages all source rows in Postgres, then publishes species and sourced
fact documents only for exact, accepted marine WoRMS species matches. Unmapped records stay
in raw storage; no taxonomy IDs, IUCN statuses, diet prose, or occurrence claims are invented.

## Next steps

1. Finish M1: expand verified taxonomy mappings, add SeaLifeBase ingestion, verify
   geographic/filter semantics and source links, add typed response schemas and persistent caching.
2. M2: implement parsing, polygon resolution, ambiguity, occurrence pagination and validation,
   accepted AphiaID normalization, depth/month/year/marine filtering, sparse-area handling,
   and deterministic weights. Aggregate counts alone must never qualify species.
3. M3: sourced cards, licensed photos, species documents, retrieval and cited guide responses.
4. M4–M5: manifest-driven Phaser scene/globe, logbook, air timer and progression.

The five eval cases only seed the future suite. The quick runner validates case structure;
it does not claim the PRD's place accuracy, citation precision or latency targets.
Authentication, player isolation, a migration runner, and production deployment
remain future work. Docker configuration is intended for local development.

## FishBase ingestion

The importer supports FishBase **v26.06** (`species`, `ecology`, `morphdat`). It verifies
checksums, pinned source URLs, required columns and species keys before connecting to the
database. Upstream `SpecCode=0` is preserved in raw storage but never published.
Morphology conflicts remain unknown; facts retain reported length types and source links.
Raw ecology/morphology rows retain stock, sex and reference fields for later retrieval work.
IUCN data and more specialized source tables are not mapped yet.

For a fresh database, Compose applies `001_initial.sql` and `002_fishbase_ingestion.sql`.
For an existing scaffold database, apply `002_fishbase_ingestion.sql` once using `psql` or
an SQL client. The importer requires both migrations and does not change schema itself.

```sh
# Download the three pinned tables and validate/prepare without writing to a database:
PYTHONPATH=backend uv run --project backend python -m app.fishbase.loader \
  --snapshot-dir backend/data/fishbase/v26.06 --release v26.06 --download \
  --worms-json backend/tests/fixtures/recorded/worms.json --dry-run

# Import the same local files into DIVEPOINT_DATABASE_URL (from .env or environment):
PYTHONPATH=backend uv run --project backend python -m app.fishbase.loader \
  --snapshot-dir backend/data/fishbase/v26.06 --release v26.06 \
  --worms-json backend/tests/fixtures/recorded/worms.json
```

Each `--worms-json` supplies captured WoRMS record(s), and can be repeated. Only exact
scientific-name matches with accepted species rank, matching valid AphiaID and marine
status are published. The included mapping covers **kelp rockfish only** (SpecCode 3950 →
AphiaID 274772). Full ingestion stages 72,430 source rows, publishing one species and seven
documents with this mapping. More species require more verified mappings.

Re-import replaces the release's raw rows and the mapped species' active FishBase documents
transactionally. Stable document IDs make repeat imports idempotent. Other providers' source
links, docs and IUCN data are preserved. An advisory lock serializes imports. Species not mapped
in the current run retain their existing published data; this is not a wholesale taxonomy refresh.
The importer never adds occurrences or creates a dive manifest. Downloads are explicit;
without `--download`, ingestion is entirely offline.

Integration tests use a temporary real PostgreSQL instance and do not require Docker:

```sh
uv sync --project backend --group integration
uv run --project backend --group integration pytest backend/tests
```

The integration test validates raw COPY, fact publication, repeat imports and rollback against
the repository's species/document DDL and ingestion migration. The embedded test server is
Postgres 18; Compose targets Postgres 16. PostGIS/globe behavior is outside these tests.
See [fixture provenance and refresh instructions](backend/tests/fixtures/recorded/README.md).
