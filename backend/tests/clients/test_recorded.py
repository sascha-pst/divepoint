import hashlib
import json
from pathlib import Path

import httpx

from app.clients.providers import (
    GBIFClient,
    INaturalistClient,
    MarineRegionsClient,
    OBISClient,
    WoRMSClient,
)
from app.config import Settings

FIXTURES = Path(__file__).parents[1] / "fixtures/recorded"
AREA = "POLYGON((-121.95 36.55,-121.85 36.55,-121.85 36.65,-121.95 36.65,-121.95 36.55))"
SETTINGS = Settings(upstream_interval_seconds=0)


def replay(name):
    body = (FIXTURES / f"{name}.json").read_bytes()
    meta = json.loads((FIXTURES / f"{name}.meta.json").read_text())
    assert hashlib.sha256(body).hexdigest() == meta["sha256"]

    def handle(request):
        expected = httpx.URL(meta["url"])
        assert request.url.host == expected.host
        assert request.url.path == expected.path
        assert sorted(request.url.params.multi_items()) == sorted(expected.params.multi_items())
        return httpx.Response(
            meta["status"], content=body, headers={"Content-Type": "application/json"}
        )

    return httpx.MockTransport(handle)


async def test_recorded_marine_regions():
    async with MarineRegionsClient(settings=SETTINGS, transport=replay("marineregions")) as client:
        rows = await client.search("Monterey Bay")
    assert rows[0]["MRGID"] == 19167
    assert rows[0]["preferredGazetteerName"] == "Monterey Bay"


async def test_recorded_obis_checklist():
    async with OBISClient(settings=SETTINGS, transport=replay("obis")) as client:
        response = await client.checklist(AREA, (0, 30))
    assert response["total"] > 0
    assert response["results"][0]["taxonID"] > 0
    assert response["results"][0]["records"] > 0


async def test_recorded_gbif_facets():
    async with GBIFClient(settings=SETTINGS, transport=replay("gbif")) as client:
        response = await client.species_counts(AREA)
    assert response["facets"][0]["field"] == "SPECIES_KEY"
    assert response["facets"][0]["counts"][0]["count"] > 0


async def test_recorded_worms_search_and_taxon():
    async with WoRMSClient(settings=SETTINGS, transport=replay("worms")) as client:
        matches = await client.search("Sebastes atrovirens")
    async with WoRMSClient(settings=SETTINGS, transport=replay("worms_taxon")) as client:
        taxon = await client.taxon(274772)
    assert matches[0] == taxon
    assert taxon.valid_AphiaID == 274772


async def test_recorded_photo_is_not_reusable():
    async with INaturalistClient(settings=SETTINGS, transport=replay("inat_taxon")) as client:
        assert await client.photo(64481) is None


def test_all_recorded_json_bodies_match_metadata():
    for path in FIXTURES.glob("*.meta.json"):
        meta = json.loads(path.read_text())
        body = path.with_name(path.name.replace(".meta.json", ".json")).read_bytes()
        assert hashlib.sha256(body).hexdigest() == meta["sha256"]
        assert meta["status"] == 200
        assert meta["captured_at"].startswith("2026-11-16")
        assert json.loads(body)
