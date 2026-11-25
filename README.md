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

## Play the prototype

After installing dependencies, run both services with one command:

```sh
./scripts/dev.sh
```

Open **http://127.0.0.1:5173**, keep **Monterey Bay**, and choose **Find my dive →
Enter the water**. Use the depth slider or ↑/↓ to descend. Click a drawn fish (or a
name in “Within reach”) to log it and open its sourced card. Cards pause the four-minute
game timer. **Surface** ends the dive and shows your discoveries. **Fishdex** persists
in this browser's local storage, across visits; it is not an account-backed logbook.

Monterey Bay, Red Sea, and Raja Ampat each have a bundled, checksum-verified occurrence
snapshot. Pick a destination and use **Any month** for the broadest sample. Red Sea and
Raja Ampat use Marine Regions areas 4264 and 21076. The packs contain a bounded sample of
OBIS records that pass area, depth, date, presence, and QC checks, with accepted WoRMS
taxonomy via OBIS and matching FishBase v26.06 facts. Each card links to individual
occurrences and source datasets. Red Sea and Raja Ampat ship without photo metadata.

Refresh a reef snapshot explicitly with
`PYTHONPATH=backend uv run --project backend python backend/scripts/capture_reef_packs.py red_sea`
or use `raja_ampat` as the argument. Capture needs internet and the local FishBase parquet
snapshot. Playing the bundled dives and opening cards use the local data.
It requires no LLM key, database setup, or live biodiversity API access to plan/play.
Species cards link to original iNaturalist photo pages when a matching photo reference
exists. The demo loads no third-party photos. Other marine place names use live Marine
Regions search and a bounded OBIS occurrence sample. Live and bundled records are checked
against the reviewed dataset list in `backend/app/checklist/sources.py`. Review new
datasets and their citation and license terms before adding them to that list. FishBase
v26.06 data is CC BY-NC 4.0 and is included for the noncommercial demo. Unknown/ambiguous names,
sparse samples, and service failures have separate UI states. Sparse dives require an
explicit player choice, and empty samples cannot be played.

Red Sea and Raja Ampat render perspective 3D meshes from bundled GEBCO_2026 depth
grids. The game scales the axes to fit the viewport and moves the view as you change
depth. Coral decorations are illustrative. The grids cover local terrain patches,
while fish evidence comes from the wider occurrence search areas. The mesh needs
no map service at play time.

To refresh the grids, install Rasterio in a capture environment and run
`python game/scripts/capture_terrain.py`. The script reads small windows by HTTP range
from the Source Cooperative GeoTIFF mirror and saves grid-cell coordinates and source
metadata in `game/src/terrain.json`.

GEBCO Bathymetric Compilation Group 2026 (2026). The GEBCO_2026 Grid.
[Dataset and citation](https://doi.org/10.5285/4f68d5c7-45eb-f999-e063-7086abc036fa)

Both services are required. Vite proxies `/v1` to FastAPI at port 8000. Compose sets the
proxy target to its `api` service. A static GitHub Pages deployment alone cannot serve
the API; this change does not deploy the game or push changes automatically.

## Current scope and limits

- Server-side place resolution, conservative text/depth/month parsing, hemisphere-aware
  seasons, place confirmation and a schematic globe centered on the resolved longitude.
- Individual OBIS occurrences are checked for location inside the displayed search bounds,
  non-land bathymetry, clean quality flags, positive species-level AphiaID, marine status,
  presence, date/year and depth. Species require accepted WoRMS-derived OBIS taxonomy.
- A manifest with log-weighted encounter sampling, depth bands and sample-relative rarity.
  Weights reflect the validated sample, **not** total abundance or real encounter probability.
- Phaser underwater scene with illustrated fish, depth controls, timer, accessible encounter
  buttons, sourced FishBase facts, photo source links, local Fishdex and dive summaries.
- Dated API fixtures and the runtime starter pack retain source metadata and checksums.
  Full downloaded FishBase snapshots stay under ignored `backend/data/`.

This is the first playable slice, not the PRD's launch-ready v1. Live search samples the
first 1,000 fish occurrences and checks up to 24 candidate species; it is not a complete
checklist. Search areas are labeled gazetteer bounding boxes or approximate 10 km point
envelopes, rather than exact marine polygons. Month filters exclude ambiguous date ranges.
Cold live searches may take up to 45 seconds; the eight-second launch target is not met
for arbitrary places. Bundled dives show the snapshot capture date.

### Ask the Guide

Open the guide from the dive or a species card. It retrieves evidence scoped to the current
dive and links each displayed statement to its source record, species page, photo, or exhibit
page. Set `DIVEPOINT_GUIDE_API_KEY` in the backend environment (or in the repository-root
`.env` for local development) to let Claude select the most relevant retrieved statements.
`DIVEPOINT_GUIDE_MODEL` optionally overrides the model. In this mode the player's question
and the retrieved statements are sent to Claude. Without a key, the guide displays a
labeled record lookup for supported questions.

The parser is deterministic rather than LLM-backed. GBIF merging, general geocoder fallback,
full taxonomy normalization, non-fish templates, authentication, persistent server
logbook/cache, and comprehensive place/guide evals remain future work. Species cards leave
unavailable facts and photos unknown. FishBase facts cover the starter species; live taxa
outside that set may have only taxonomy and occurrence evidence. Sprites and scenery are
stylized, with approximate colors and movement, and are not identification/behavior claims.

## Next steps

1. Validate the UI in a connected browser and broaden the reviewed place set.
2. Add complete occurrence pagination, GBIF merging and persistent caching; benchmark live latency.
3. Connect the ingested Postgres species documents to broaden the cited guide.
4. Replace the schematic globe and generic fish templates with richer geographic/species art.

The quick eval runs the guide API against bundled recorded dives with external HTTP blocked
and the model disabled. It checks each cited statement and exact source URL, or the expected
no-data response. Add cases to `evals/guide.jsonl`; each evidence entry contains a topic,
source URL, and statement. Place seeds still receive a format check. Backend tests run without
public HTTP. PostgreSQL integration tests are optional.

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
