# PRD — Divepoint: Describe a Place, Dive It, Meet What Lives There

Nov 16, 2026 · @Sash

## 1. Overview

Divepoint (working name) is an exploration game: the player describes a place in the world in plain language, the game builds a dive there, and every creature they meet is a real species with recorded sightings in that place. It is a RAG system over open biodiversity APIs, so the dive is generated from data, not invented.

**Example.** "Take me to the kelp forest off Monterey, 15 metres, in autumn." The game resolves the place, pulls species recorded there at that depth and season, and drops the player into a dive where sea otters, kelp rockfish and señoritas appear at rates that match the records. Tapping a fish opens a species card with sourced facts; asking the dive guide "Why is this fish orange?" gets an answer grounded in those sources.

**Problem.** Ocean biodiversity data is rich and open but locked in research APIs. Dive and fish games are fun but use made-up or generic species lists. Nothing lets a curious person say "show me what lives in Raja Ampat" and actually explore it.

**Goals (v1)**

1. Any recognisable marine place typed by a player resolves to an area and produces a dive within 8 seconds.
2. 100% of species shown have at least one occurrence record inside the dive area; the game can show that evidence.
3. Species facts and guide answers come only from retrieved source records, with citations.
4. Players return to collect species in a logbook ("Fishdex") across many places.

**Non-goals (v1)**

- Photorealistic 3D models for each species (not feasible for tens of thousands of taxa); v1 draws species as 2D illustrations and shows real licensed photos on cards.
- Freshwater dives (P1, via GBIF).
- Multiplayer, trading or monetisation.
- Real dive-planning or safety advice: this is a game, not a dive computer.

## 2. Players and core loop

The primary player is a curious non-diver aged 12+ who wants to explore; the secondary players are real divers previewing a trip and teachers using it in class.

| Player | Motivation | What keeps them playing |
| --- | --- | --- |
| Explorer (primary) | "What lives there?" curiosity, armchair travel | Discovering rare species, filling the Fishdex, new places |
| Trip-planning diver | Preview the fauna of a real dive site before going | Accurate species lists by depth and season |
| Teacher / student | Biodiversity and geography lessons | Comparing places, sourced facts they can cite |

**Core loop**

1. **Describe** a place in words ("the Blue Hole in Belize", "a wreck in the Red Sea at 30 m").
2. **Confirm** the resolved spot on a globe; the guide asks only if the place is ambiguous or data is thin.
3. **Dive**: descend through depth zones; species appear in proportion to how often they are recorded there.
4. **Encounter**: tap a creature to log it and open its species card; ask the guide questions.
5. **Surface**: see a dive summary (species logged, rarities, new Fishdex entries) and pick the next place.

**Key user stories**

- As an explorer, I type "coral reef in the Maldives" and within seconds I am diving among reef fish actually recorded there.
- As an explorer, I type "Blue Hole" and the guide asks: Belize or Dahab, Egypt?
- As a diver, I set depth to 25 m and season to March and the species list changes to match.
- As a student, I tap a manta ray and see its depth range, diet and conservation status, each with a source link.
- As any player, if I pick an area with few records, the game tells me and offers to widen the search area.

## 3. Open data sources

Six free sources cover the whole pipeline: a gazetteer turns words into an area, occurrence APIs say what lives there, and taxonomy and species databases supply the facts and photos. All allow reuse with attribution; licences per photo must be checked.

| Source | Role in the game | Access | Key calls / notes |
| --- | --- | --- | --- |
| [Marine Regions gazetteer](https://docs.ropensci.org/mregions2/reference/gaz_rest_records_by_name.html) | Place name → MRGID + polygon (seas, reefs, EEZs, bays) | REST, no key | `getGazetteerRecordsByName` (fuzzy match), geometry by MRGID, reverse lookup by lat/long |
| [OBIS](https://iobis.github.io/pyobis/checklist.html) | What marine species are recorded in an area | REST `api.obis.org/v3`, no key | `/checklist` with WKT `geometry`, depth and date filters; `/occurrence`; `/facet` for counts |
| [GBIF](https://docs.ropensci.org/rgbif/articles/occ_counts.html) | Second occurrence source; freshwater (P1); seasonal counts | REST `api.gbif.org/v1`, no key for search | `/occurrence/search` with `geometry` and `facet=speciesKey`, `limit=0` for counts only |
| [WoRMS](https://www.marinespecies.org/aphia.php?p=soap) | Canonical taxonomy: one AphiaID per species, synonyms, common names | REST `marinespecies.org/rest`, no key, CC BY | `AphiaRecordByAphiaID`, `AphiaRecordsByName`; OBIS already keys on AphiaID |
| [FishBase / SeaLifeBase](https://docs.ropensci.org/rfishbase/) | Species facts: depth range, size, diet, habitat, danger to humans | Parquet tables on Source Cooperative S3, read with DuckDB | 2026 releases tagged v26.06; \~35k fish species plus non-fish aquatic life in SeaLifeBase |
| [iNaturalist](https://pyinaturalist.readthedocs.io/en/main/modules/pyinaturalist.v1.taxa.html) | Species photos for cards and sprites reference | REST `api.inaturalist.org/v1` | `/taxa` returns default photo with `license_code` and `attribution`; keep only CC0 / CC BY / CC BY-SA unless the game is non-commercial |

**Notes on access**

- The FishBase REST API used by older tutorials is gone; [rfishbase](https://packages.ropensci.org/rfishbase/NEWS) now reads parquet snapshots, so we mirror the tables we need into our own database instead of calling an API at play time.
- OBIS covers marine species only, keyed on WoRMS AphiaIDs; GBIF uses its own backbone taxonomy, so GBIF results are mapped to AphiaIDs through WoRMS name matching.
- All six are rate-limited public services: cache aggressively and never call them from the client.

## 4. Functional requirements

P0 is required for v1; P1 ships next; P2 is backlog.

| ID | Area | Requirement | Priority |
| --- | --- | --- | --- |
| FR-1 | Place | Parse a free-text dive request into place, depth (m), season/month and habitat hint using an LLM with structured output | P0 |
| FR-2 | Place | Resolve place via Marine Regions; fall back to a general geocoder plus a buffer (default 10 km radius) for named dive sites not in the gazetteer | P0 |
| FR-3 | Place | If more than one strong match (e.g. "Blue Hole"), ask the player to choose; show the chosen area on a globe before diving | P0 |
| FR-4 | Species | Build a checklist from OBIS (and GBIF) for the area, filtered by depth band and, when given, months | P0 |
| FR-5 | Species | Normalise every taxon to a WoRMS AphiaID; merge OBIS and GBIF counts per species | P0 |
| FR-6 | Species | Drop records with no species-level ID, land points, and records older than a configurable year (default 1970) | P0 |
| FR-7 | Species | If fewer than 15 species are found, tell the player and offer to widen the radius or depth band | P0 |
| FR-8 | Dive | Generate a dive manifest: species with encounter weights from record counts, depth zone and rarity tier | P0 |
| FR-9 | Dive | Render a 2D dive scene with depth zones; every species appears as a drawn sprite (hero, template or group tier, Section 6), spawned by manifest weights | P0 |
| FR-10 | Cards | Tapping a sprite opens a photo card: real licensed photo with credit, common and scientific name, size, depth range, diet, IUCN status and "seen here" evidence; every fact and the photo link out to their source page | P0 |
| FR-11 | Guide | In-dive guide answers questions using only retrieved species and place documents, with citations; says "no data" otherwise | P0 |
| FR-12 | Logbook | Fishdex stores every species logged, where and when; shows completion by region and taxon group | P0 |
| FR-13 | Caching | Cache place resolutions and checklists for 30 days; species cards until the next data release | P0 |
| FR-14 | Season | Month filter uses GBIF/OBIS event dates; flag migratory species (e.g. whale sharks) as seasonal | P1 |
| FR-15 | Freshwater | Freshwater dives (lakes, rivers, cenotes) from GBIF + FishBase | P1 |
| FR-16 | Social | Shareable dive postcards with the species found | P1 |
| FR-17 | Classroom | Teacher mode: preset places, comparison view, printable species sheets | P2 |

## 5. Architecture and RAG design

Two kinds of retrieval drive the game: live occurrence queries decide which species are in the dive, and a vector index of species documents grounds every card and guide answer.

&#91;embedded content: architecture · play path and offline species knowledge\]

An ambiguous place loops back to the player; once the area is fixed, code (not the LLM) queries OBIS and GBIF and builds the manifest, and cards and guide answers retrieve from the offline species index.

**Play path, step by step**

1. **Parse.** The LLM turns "wreck dive in the Red Sea at 30 m in May" into `{place: "Red Sea", habitat: "wreck", depth_m: 30, month: 5}`.
2. **Resolve.** Marine Regions fuzzy search returns candidate areas; more than one strong match → clarify. Point-like dive sites get a buffered polygon.
3. **Retrieve occurrences.** OBIS `/checklist` and GBIF `/occurrence/search` with the WKT polygon and depth/date filters, run in parallel, results cached.
4. **Normalise and weight.** Map to AphiaIDs via WoRMS, merge counts, apply depth-zone and season factors, assign rarity.
5. **Play.** The client renders the manifest; species cards and the guide pull from the species index.

**What the RAG index holds**

- One short document per species fact (diet, size, depth range, habitat, behaviour notes, IUCN status), each with source, release version and URL.
- Place documents from Marine Regions (type, parent sea, area) so the guide can answer "What is this place?".
- The guide prompt receives the current dive manifest plus top-k retrieved docs filtered to species in this dive; it must cite doc IDs and say "no data" when nothing matches.

**Caching and freshness**

- Place and checklist results cached 30 days; popular places pre-warmed nightly.
- Species docs rebuilt when FishBase/SeaLifeBase or WoRMS publish a new release.

## 6. Game design

The data decides what appears and how often; the game design decides how it feels. Rules below keep the dive fun without breaking accuracy.

**Depth zones.** A dive is split into zones; each species is placed in zones that overlap both its recorded depths in the area and its FishBase depth range.

| Zone | Depth | Feel |
| --- | --- | --- |
| Surface | 0–5 m | Bright, schooling fish, snorkel-level life |
| Reef / kelp | 5–30 m | Densest life, most encounters |
| Wall / drop-off | 30–60 m | Larger pelagics, fewer but bigger encounters |
| Twilight (bonus) | 60–200 m | Unlockable "submersible" mode, rare deep species |

**Encounter weighting.** For species *s* in the dive area, weight = log(1 + records of *s*) × depth-match factor × season factor. Logs stop common species from flooding the scene while keeping rare ones rare. Each scene samples 8–20 species from these weights.

**Rarity tiers** (by percentile of weight within the area): Common (top 50%), Uncommon (next 30%), Rare (next 15%), Legendary (bottom 5%, or IUCN Endangered/Critically Endangered). Rarity is per place: a whale shark is Legendary in most areas but Uncommon at Ningaloo in season.

**Scoring and progression**

- Points for each species logged, weighted by rarity; first-ever log of a species gives a Fishdex bonus.
- Badges by taxon group (sharks, nudibranchs, cephalopods) and by region (Coral Triangle, Mediterranean).
- Air supply limits dive length (about 4 minutes of play), creating a reason to come back.

**Accuracy rules the game must never break**

1. A species appears only if it has at least one qualifying occurrence record in the area.
2. No invented behaviours in text: guide and card text come from retrieved sources.
3. Sprites may be stylised, but each species card shows a real licensed photo with credit and a link to its source page.
4. Deep or dangerous species are labelled factually, without sensationalism.

**Art: drawn species, real photo cards.** In the dive, every creature is a drawn sprite so the scene feels like one game; tapping it flips to a photo card showing what the animal really looks like, with links to the sources. Hand-drawing tens of thousands of species is not feasible, so sprites come in tiers.

| Tier | Covers | How it is made | Launch size |
| --- | --- | --- | --- |
| Hero | Most-encountered species across the top 50 places | Commissioned illustrations with idle + swim animation | \~150 species |
| Template | All other fish with FishBase morphology data | Procedural sprite: body template chosen from FishBase morphology fields (lateral body shape, cross section, mouth position, tail shape), scaled by max length, tinted with a per-family palette | Thousands, generated |
| Group | Non-fish: turtles, rays, octopus, nudibranchs, corals, dolphins, etc. | One illustrated template per group, tinted per species family | \~40 templates |
| Fallback | Anything with no morphology or group match | Neutral silhouette marked "?" | As needed |

FishBase's [MORPHOLOGY table](https://fishbase.se/manual/FishBaseThe_MORPHOLOGY_Table.htm) stores standard multiple-choice descriptors per species (for example [body shape "fusiform / normal" and cross section "compressed"](https://fishbase.mnhn.fr/physiology/Ilisha_elongata)), which is what drives template selection. Template colours are approximate, which is exactly why the photo card is one tap away.

**Photo card, top to bottom**

1. **Photo** from iNaturalist (allowed licence only), credit line "© photographer, licence" linking to the iNaturalist photo page.
2. **Names**: common name; scientific name links to the species' WoRMS page.
3. **Facts**: size, depth range, diet, habitat, IUCN status; each row has a small source icon linking to the exact page it came from (FishBase summary, WoRMS record).
4. **Seen here**: record count and latest year in this area, linking to the species' OBIS and GBIF pages.
5. **Ask the guide** button; answers cite the same sources.

Links open in an in-app browser and pause the air timer. Link templates: `fishbase.se/summary/{SpecCode}`, `marinespecies.org/aphia.php?p=taxdetails&id={AphiaID}`, `obis.org/taxon/{AphiaID}`, `gbif.org/species/{key}`, `inaturalist.org/photos/{photo_id}` (confirm each in M1).

## 7. API, data model and contracts

The game client talks only to our backend; the backend owns all calls to the open APIs, the cache and the LLM.

**Endpoints**

| Method | Path | Purpose |
| --- | --- | --- |
| POST | /v1/dives/plan | Free text in → `clarify` (ambiguous place) or a resolved place + dive manifest |
| GET | /v1/dives/{id} | Fetch a saved dive manifest |
| GET | /v1/species/{aphia\_id} | Photo card: photo + credit, facts, and a source URL per fact |
| POST | /v1/dives/{id}/ask | Ask the guide; streams answer tokens and citations (SSE) |
| POST | /v1/logbook | Log an encounter |
| GET | /v1/logbook | Player's Fishdex and badges |

**Dive manifest** (returned by `/dives/plan`)

```json
{
  "type": "dive",                     // or "clarify" | "too_sparse"
  "place": {"name": "Monterey Bay", "mrgid": 18573, "source": "marineregions",
            "geometry_wkt": "POLYGON((...))"},
  "filters": {"depth_m": [0, 20], "months": [9, 10, 11]},
  "species": [
    {"aphia_id": 0, "name": "Sebastes atrovirens", "common": "Kelp rockfish",
     "zone": "reef", "weight": 4.2, "rarity": "common",
     "evidence": {"obis_records": 0, "gbif_records": 0, "latest_year": 0}}
  ],
  "clarify": null
}
```

IDs and counts above are placeholders; real values come from the APIs.

**Data model**

| Table | Key fields |
| --- | --- |
| places | id, query\_text, mrgid, name, geometry (PostGIS), source, resolved\_at |
| checklists | place\_id, depth\_min, depth\_max, months, aphia\_id, obis\_count, gbif\_count, latest\_year, fetched\_at |
| species | aphia\_id, scientific\_name, common\_names\[\], fishbase\_spec\_code, gbif\_key, inat\_taxon\_id, depth\_min, depth\_max, max\_length\_cm, iucn\_status, body\_shape, cross\_section, tail\_shape, source\_urls (jsonb) |
| species\_docs | id, aphia\_id, source (fishbase, worms, inat, obis), field, text, url, embedding, release\_version |
| photos | aphia\_id, url, license\_code, attribution, photo\_page\_url |
| dives | id, player\_id, place\_id, filters, manifest\_json, created\_at |
| encounters | id, dive\_id, player\_id, aphia\_id, logged\_at |
| sprites | aphia\_id, tier (hero / template / group / fallback), template\_id, palette, asset\_url, animation\_url |

## 8. Evaluation and guardrails

Launch is gated on a 200-prompt place set and a 150-question guide set passing the targets below; both run in CI on every prompt or pipeline change.

**Eval sets**

- **Places (200):** famous dive sites, seas, vague phrases ("somewhere warm with turtles"), ambiguous names, misspellings, and 20 land or nonsense inputs that must be rejected.
- **Guide questions (150):** answerable from species docs, needing a place fact, and out-of-scope questions that must get "no data".
- **Expert spot-check:** a marine biologist or experienced diver reviews 30 generated dives from well-known sites for plausibility.

| Metric | How measured | v1 target |
| --- | --- | --- |
| Place resolution accuracy | Resolved area contains the intended site | ≥ 90% |
| Clarify precision | Asks only when the name is truly ambiguous | ≥ 85% |
| Species validity | Species in manifest with ≥ 1 qualifying record in area | 100% |
| Expert plausibility | Reviewer rates dive "realistic" (1–5 scale) | mean ≥ 4.0 |
| Guide citation precision | Cited passage supports the sentence (LLM judge + 10% human) | ≥ 95% |
| Correct "no data" | Out-of-scope guide questions | ≥ 90% |
| Photo licence compliance | Photos with allowed licence + attribution shown | 100% |
| Time to dive (p95) | Prompt submitted → scene playable, cold cache | ≤ 8 s |
| Day-7 retention | Players who return within 7 days | ≥ 25% |

**Guardrails**

- The LLM never adds species to a manifest; it only parses the request and narrates. Species lists come from code that queries the APIs.
- The guide answers from retrieved `species_docs` and place records only, cites them, and refuses to invent behaviour or facts.
- Real-world safety questions ("Is it safe to dive here?") get a fixed message that the game is not dive guidance.
- Sensitive species locations: hide exact record coordinates for IUCN threatened species; show area-level presence only.
- API etiquette: per-source rate limiting, a descriptive User-Agent, and an attribution screen crediting OBIS, GBIF, WoRMS, FishBase/SeaLifeBase, Marine Regions and iNaturalist photographers.

## 9. Build plan for Claude Code

Build data-first in five milestones: a correct species list matters more than graphics, so the game shell comes last. Each milestone ends with a test you can run.

**Repo structure**

```
divepoint/
  CLAUDE.md                  # rules for Claude Code (below)
  docs/PRD.md                # export of this doc
  backend/
    app/
      api/                   # FastAPI routers: dives, species, guide, logbook
      clients/               # marineregions.py, obis.py, gbif.py, worms.py, inat.py
      fishbase/              # DuckDB loader for FishBase/SeaLifeBase parquet
      place/                 # LLM request parser, place resolver, clarify logic
      checklist/             # merge, filter, AphiaID normalise, weights, rarity
      rag/                   # species_docs builder, embeddings, retriever, guide prompt
      cache/
    tests/
      fixtures/              # recorded API responses (no live calls in CI)
  evals/
    places.jsonl  guide.jsonl  run_evals.py
  game/                      # Phaser 3 (or PixiJS) web client + globe picker
  docker-compose.yml         # postgres+postgis+pgvector, api, game
```

**Milestones**

1. **M1 — API clients and cache.** Typed clients for Marine Regions, OBIS, GBIF, WoRMS, iNaturalist; FishBase parquet loaded into Postgres; recorded fixtures. Done when: `pytest tests/clients` passes offline.
2. **M2 — Place to checklist.** Request parser, place resolver with clarify, checklist merge, filters, weights and rarity. Done when: place accuracy ≥ 90% and species validity 100% on the eval set.
3. **M3 — Species cards and RAG guide.** Build `species_docs` from FishBase, WoRMS and OBIS fields; embed; guide with citations and "no data". Done when: guide citation precision ≥ 95%.
4. **M4 — Game client.** Globe picker, 2D dive scene with depth zones, sprite pipeline (hero art, morphology templates, group templates), encounter tap → photo card with source links, air timer. Done when: a full dive plays end to end from a typed prompt.
5. **M5 — Progression and polish.** Fishdex, rarity points, badges, dive summary, attribution screen, expert spot-check. Done when: all Section 8 targets pass.

**Suggested stack** (swap freely): Python 3.12 + FastAPI, httpx, DuckDB for FishBase parquet, Postgres 16 + PostGIS + pgvector, Claude via the Anthropic API for parsing and the guide, Phaser 3 + TypeScript for the game, pytest + Playwright.

**Starter CLAUDE.md**

```markdown
# Divepoint — rules for Claude Code
- Read docs/PRD.md first; work on one milestone per session.
- The LLM never decides which species appear. Species come from OBIS/GBIF queries in backend/app/checklist.
- Every species is keyed by WoRMS AphiaID.
- No live API calls in tests: record fixtures in tests/fixtures.
- Only show photos with allowed licences, always with attribution.
- Run `pytest` and `python evals/run_evals.py --quick` before calling a task done.
```

**Tips for working in Claude Code**

- Tip: begin with "Read docs/PRD.md and CLAUDE.md, then plan M1" so it plans before coding.
- Tip: in M1, have it hit each API once and save the JSON as fixtures; build everything else against those files.
- Tip: write 20 eval places you know well (Great Barrier Reef, Monterey, Red Sea) in M1 so M2 has a target from day one.
- Tip: keep the game client dumb: it renders the manifest and never computes species, so you can swap engines later.

## Open questions

- [ ] Hero sprites: how many to commission for launch (\~150 proposed), and who checks them for accuracy?
- [ ] Commercial or non-commercial? This decides which iNaturalist photo licences (CC BY-NC) are allowed.
- [ ] Should land-locked or nonsense places get a playful refusal or a "nearest sea" suggestion?
- [ ] Platform: web first, then mobile? Offline packs for popular places?
- [ ] How to handle sparse regions (much of the deep sea and parts of Africa) without the game feeling empty?
- [ ] Age rating and whether accounts are needed for the Fishdex.
