# Recorded biodiversity responses

These are real upstream responses captured on 2026-11-16. JSON response bodies are
saved without normalization. Every `.meta.json` records the exact request URL,
capture timestamp and SHA-256 of its paired body. Files contain no authentication
headers or exact sensitive-species occurrence coordinates.

- `marineregions`: Monterey Bay name search (actual MRGID **19167**).
- `obis`: checklist discovery query for a small Monterey polygon and depth/date filters.
- `gbif`: species-key facet discovery query for the same polygon.
- `worms`, `worms_taxon`: search and accepted record for *Sebastes atrovirens*, AphiaID **274772**.
- `inat`, `inat_taxon`: taxon search and ID **64481**. The default photo has no reusable
  license and must be excluded. No photo image files are downloaded.

These responses test API contracts, not geographic/species validity. Checklists and
facets may be truncated and are insufficient evidence for a manifest. M2 must verify
individual qualifying occurrences, depth/month semantics, pagination and normalization.
Raw upstream response fields and associated attributions remain intact.

`fishbase/v26.06` contains real parquet rows selected from the published FishBase
snapshot for SpecCodes 2, 3 and 3950, with all upstream columns preserved. There are
3 species, 6 ecology and 10 morphology rows. Sidecars include both the full upstream
file checksum and the derived fixture checksum and predicate. No facts were synthesized.
These small files are for offline tests; full local snapshots live in ignored `backend/data/`.

Refresh API fixtures explicitly (live network):

```sh
backend/.venv/bin/python backend/scripts/capture_fixtures.py
# To retry one source:
backend/.venv/bin/python backend/scripts/capture_fixtures.py --source worms
```

Regenerate parquet subsets after downloading the pinned snapshot:

```sh
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/subset_fishbase_fixtures.py \
  --source backend/data/fishbase/v26.06 \
  --output backend/tests/fixtures/recorded/fishbase/v26.06 --release v26.06
```

Source access protocol: [rfishbase](https://github.com/ropensci/rfishbase/blob/master/R/fb_tbl.R).
Release notes: [v26.06](https://ropensci.r-universe.dev/rfishbase/NEWS).
Retain FishBase attribution when reusing these facts; photo licensing is separate.
