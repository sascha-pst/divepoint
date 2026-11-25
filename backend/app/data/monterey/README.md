# Recorded Monterey starter dive

Captured from Marine Regions, OBIS and iNaturalist on 2026-11-16. FishBase rows
come from the verified v26.06 species parquet snapshot via Source Cooperative.
`provenance.json` records request URLs, timestamps, response hashes, the FishBase
parent hash, and hashes of the local derived JSON files. JSON is reserialized. Photo references retain only matching species and photo IDs. Regenerate explicitly with:

```sh
backend/.venv/bin/python backend/scripts/capture_playable.py
```

This command calls public APIs and needs `backend/data/fishbase/v26.06/species.parquet`.
It samples 1,000 OBIS teleost records, fetches taxonomy/photo metadata for 24 candidates,
and selects FishBase rows by exact scientific name. This is intentionally not exhaustive.
The application revalidates raw occurrences and accepted taxonomy for every plan, and
checks pack file hashes at startup. At 0–30 m, 23 species pass all current filters.
Occurrence counts and rarity reflect only this bounded sample. Some candidate records
are rejected by FishBase depth range intersection or taxonomy validation.

Coordinates exist only in these server-side source records. Client manifests and cards
expose area-level location plus source record/dataset links, never occurrence coordinates.
This data does not bypass the validity checks and is not an invented demonstration.

Attribution: OBIS (Ocean Biodiversity Information System) and the original dataset
citations and licenses linked in each encounter's evidence; WoRMS (World Register of
Marine Species) taxonomy via OBIS; Marine Regions gazetteer; Froese, R. and D. Pauly,
editors, FishBase v26.06 (CC BY-NC 4.0). Cards link to matching iNaturalist photo pages.
The photo pages contain the photographer credit and license information.
