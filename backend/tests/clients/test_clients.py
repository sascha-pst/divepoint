import json
from pathlib import Path

import httpx
import pytest

from app.clients.providers import (
    GBIFClient,
    INaturalistClient,
    MarineRegionsClient,
    OBISClient,
    WoRMSClient,
)
from app.config import Settings

SETTINGS = Settings(upstream_interval_seconds=0)


async def test_taxon_is_typed_and_cached():
    fixture = json.loads(
        (Path(__file__).parents[1] / "fixtures/worms_taxon.synthetic.json").read_text()
    )
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json=fixture)

    async with WoRMSClient(settings=SETTINGS, transport=httpx.MockTransport(handle)) as client:
        assert (await client.taxon(999999999)).rank == "Species"
        await client.taxon(999999999)
    assert len(requests) == 1
    assert requests[0].url.path == "/rest/AphiaRecordByAphiaID/999999999"
    assert "Divepoint" in requests[0].headers["User-Agent"]


@pytest.mark.parametrize(
    "license_code,attribution,allowed",
    [
        ("cc0", "Test photographer", True),
        ("cc-by", "Test photographer", True),
        ("cc-by-sa", "Test photographer", True),
        ("cc-by-nc", "Test photographer", False),
        (None, "Test photographer", False),
        ("cc-by", "", False),
    ],
)
async def test_photo_requires_license_and_credit(license_code, attribution, allowed):
    payload = {
        "results": [
            {
                "default_photo": {
                    "id": 1,
                    "url": "https://example.test/photo.jpg",
                    "license_code": license_code,
                    "attribution": attribution,
                }
            }
        ]
    }
    async with INaturalistClient(
        settings=SETTINGS,
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)),
    ) as client:
        photo = await client.photo(1)
    assert (photo is not None) == allowed
    if photo:
        assert photo.photo_page_url.endswith("/photos/1")


async def test_upstream_errors_are_not_cached():
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(404, json={"error": "missing"})

    async with WoRMSClient(settings=SETTINGS, transport=httpx.MockTransport(handle)) as client:
        for _ in range(2):
            with pytest.raises(httpx.HTTPStatusError):
                await client.taxon(1)
    assert len(calls) == 2


async def test_rate_limit_retries():
    calls = []

    def handle(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"results": []})

    async with INaturalistClient(
        settings=SETTINGS, transport=httpx.MockTransport(handle)
    ) as client:
        assert await client.photo(1) is None
    assert len(calls) == 2


async def test_discovery_request_parameters():
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={"results": []})

    transport = httpx.MockTransport(handle)
    async with OBISClient(settings=SETTINGS, transport=transport) as client:
        await client.checklist("POLYGON TEST", (0, 30))
    assert requests[-1].url.params["startdepth"] == "0"
    assert requests[-1].url.params["startdate"] == "1970-01-01"
    async with GBIFClient(settings=SETTINGS, transport=transport) as client:
        await client.species_counts("POLYGON TEST")
    assert requests[-1].url.params["hasGeospatialIssue"] == "false"
    assert requests[-1].url.params["facet"] == "speciesKey"
    async with MarineRegionsClient(settings=SETTINGS, transport=transport) as client:
        await client.search("Monterey Bay")
    assert requests[-1].url.params["fuzzy"] == "true"
