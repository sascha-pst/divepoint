import copy
import json
from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from app.checklist.manifest import accepted_taxon, build_species, qualify
from app.checklist.service import DiveService, read_pack
from app.main import app
from app.place.parser import parse_request, season_months
from app.place.resolver import area_from_record

PLACE = area_from_record(read_pack("place"))
FILTERS = {"depth_m": [0, 30], "months": []}
RECORDS = read_pack("occurrences")["results"]


@pytest.fixture
def record():
    return copy.deepcopy(qualify(RECORDS, PLACE, FILTERS)[0])


@pytest.mark.parametrize(
    "changes",
    [
        {"decimalLatitude": 0},
        {"decimalLongitude": 0},
        {"decimalLatitude": None},
        {"depth": None},
        {"depth": -1},
        {"depth": 100},
        {"depth": float("nan")},
        {"bathymetry": 3},
        {"bathymetry": None},
        {"flags": ["ON_LAND"]},
        {"flags": None},
        {"marine": False},
        {"marine": None},
        {"absence": True},
        {"absence": None},
        {"dropped": True},
        {"dropped": None},
        {"occurrenceStatus": "absent"},
        {"date_start": -1},
        {"date_end": 9999999999999},
        {"date_start": None},
        {"speciesid": None},
        {"aphiaID": 1},
        {"id": None},
    ],
)
def test_bad_records_never_qualify(record, changes):
    record.update(changes)
    assert qualify([record], PLACE, FILTERS) == []


def test_duplicates_are_counted_once(record):
    assert len(qualify([record, record], PLACE, FILTERS)) == 1


def test_month_filter_uses_unambiguous_record_dates(record):
    month = datetime.fromtimestamp(record["date_start"] / 1000, UTC).month
    assert qualify([record], PLACE, {**FILTERS, "months": [month]})
    assert not qualify([record], PLACE, {**FILTERS, "months": [month % 12 + 1]})
    record["date_end"] = record["date_start"] + 365 * 86400 * 1000
    assert not qualify([record], PLACE, {**FILTERS, "months": [month]})


def test_no_taxonomy_means_no_species(record):
    assert build_species([record], {}, {}, FILTERS) == []


@pytest.mark.parametrize(
    "change",
    [
        {"taxonRank": "Genus"},
        {"taxonomicStatus": "unaccepted"},
        {"is_marine": False},
        {"acceptedNameUsageID": -1},
        {"is_terrestrial": True},
    ],
)
def test_unaccepted_taxa_cannot_spawn(change):
    taxon = copy.deepcopy(next(iter(read_pack("taxa").values())))
    taxon.update(change)
    assert not accepted_taxon(taxon)


def test_prompt_parser_and_hemisphere_seasons():
    parsed = parse_request(
        "Take me to the kelp forest off Monterey, 15 metres, in autumn.", 30, None
    )
    assert parsed == {"place": "monterey", "depth_m": [0, 15.0], "months": [], "season": "autumn"}
    assert season_months("autumn", 36) == [9, 10, 11]
    assert season_months("autumn", -30) == [3, 4, 5]
    assert parse_request("Red Sea at 30 m in May", 15, None)["months"] == [5]
    with pytest.raises(ValueError):
        parse_request("Monterey at 200m", 30, None)


def test_reversed_gazetteer_longitudes_are_sorted():
    assert PLACE["bounds"] == [-122.12, 36.57, -121.74, 37.02]
    assert PLACE["mrgid"] == 19167


def test_playable_routes_use_only_verified_pack_and_card_sources():
    with TestClient(app) as client:
        result = client.post("/v1/dives/plan", json={"text": "Monterey Bay"}).json()
        assert result["type"] == "dive"
        assert len(result["species"]) >= 15
        ids = {row["aphia_id"] for row in result["species"]}
        assert len(ids) == len(result["species"])
        assert all(
            row["weight"] > 0 and row["evidence"]["obis_records"] > 0 for row in result["species"]
        )
        # Exact occurrence locations must never leak to the client manifest.
        assert "decimalLatitude" not in json.dumps(result)
        assert client.get(f"/v1/dives/{result['id']}").json() == result
        for species in result["species"]:
            card = client.get(f"/v1/species/{species['aphia_id']}?dive_id={result['id']}").json()
            assert card["name"] == species["name"]
            assert all(
                fact["source_url"].startswith("https://www.fishbase.se/summary/")
                for fact in card["facts"]
            )
            assert card["photo"] is None
            if species["common"] == "Blue rockfish":
                assert card["photo_link"].startswith("https://www.inaturalist.org/photos/")
            assert {credit["source_url"] for credit in card["dataset_credits"]} == set(
                species["evidence"]["dataset_urls"]
            )
            assert all(
                credit["license"] in {"CC BY 4.0", "CC0 1.0"}
                and credit["license_url"].startswith("https://creativecommons.org/")
                for credit in card["dataset_credits"]
            )
            assert card["evidence"]["record_urls"]
        assert client.get(f"/v1/species/1?dive_id={result['id']}").status_code == 404
        assert client.get("/v1/dives/missing").status_code == 404
        assert client.post("/v1/dives/plan", json={"text": "Monterey at 100m"}).status_code == 422


def test_depth_and_month_really_change_the_manifest():
    with TestClient(app) as client:
        shallow = client.post("/v1/dives/plan", json={"text": "Monterey Bay", "depth_m": 1}).json()
        assert shallow["type"] == "too_sparse"
        deeper = client.post(
            "/v1/dives/plan", json={"text": "Monterey Bay", "depth_m": 30, "month": 7}
        ).json()
        assert deeper["filters"]["months"] == [7]
        assert shallow["species"] != deeper["species"]


async def test_live_place_ambiguity_and_invalid_selection(monkeypatch):
    service = DiveService()
    rows = [
        read_pack("place"),
        dict(read_pack("place"), MRGID=999, accepted=999, preferredGazetteerName="Other test bay"),
    ]

    async def search(name):
        return rows

    monkeypatch.setattr(service.marine, "search", search)
    from fastapi import HTTPException

    from app.api.dives import PlanRequest

    try:
        response = await service.plan(PlanRequest(text="Test Bay"))
        assert response["type"] == "clarify"
        assert len(response["candidates"]) == 2
        with pytest.raises(HTTPException, match="422"):
            await service.plan(PlanRequest(text="Test Bay", place_id=-1))
    finally:
        await service.close()


async def test_live_occurrences_are_validated_and_taxa_fetched(monkeypatch):
    service = DiveService()
    calls = []
    payload = read_pack("occurrences")

    async def search(name):
        return [read_pack("place")]

    async def get(path, params=None):
        calls.append(path)
        if path == "occurrence":
            return payload
        taxon = read_pack("taxa").get(path.split("/")[-1])
        return {"results": [taxon] if taxon else []}

    monkeypatch.setattr(service.marine, "search", search)
    monkeypatch.setattr(service.obis, "get", get)
    from app.api.dives import PlanRequest

    try:
        result = await service.plan(PlanRequest(text="Test Bay"))
        assert result["source_mode"] == "live"
        assert result["species"]
        assert calls[0] == "occurrence"
        assert any(path.startswith("taxon/") for path in calls)

        candidate = copy.deepcopy(qualify(payload["results"], PLACE, FILTERS)[0])
        unknown = {**candidate, "dataset_id": "unreviewed", "license": "cc-by"}
        restricted = {**candidate, "license": "https://creativecommons.org/licenses/by-nc/4.0/"}
        payload = {"results": [unknown, restricted]}
        calls.clear()
        result = await service.plan(PlanRequest(text="Test Bay"))
        assert result["type"] == "too_sparse"
        assert result["species"] == []
        assert calls == ["occurrence"]
    finally:
        await service.close()


def test_upstream_outage_returns_actionable_error(monkeypatch):
    with TestClient(app) as client:

        async def fail(name):
            raise httpx.ConnectError("offline")

        monkeypatch.setattr(app.state.dives.marine, "search", fail)
        result = client.post("/v1/dives/plan", json={"text": "Unbundled Bay"})
        assert result.status_code == 503
        assert "Monterey" in result.json()["detail"]


def test_taxonomy_response_cannot_change_the_occurrence_id(record):
    key = str(record["speciesid"])
    taxon = copy.deepcopy(next(iter(read_pack("taxa").values())))
    taxon.update(taxonID=99999999, acceptedNameUsageID=99999999)
    assert build_species([record], {key: taxon}, {}, FILTERS) == []


def test_guide_links_to_exact_dive_records(monkeypatch):
    monkeypatch.delenv("DIVEPOINT_GUIDE_API_KEY", raising=False)
    with TestClient(app) as client:
        dive = client.post("/v1/dives/plan", json={"text": "Monterey Bay"}).json()
        fish = next(s for s in dive["species"] if s["common"] == "Blue rockfish")
        path = f"/v1/dives/{dive['id']}/ask"
        answer = client.post(path, json={"question": "Has Blue rockfish been recorded here?"})
        assert answer.status_code == 200
        assert answer.json()["evidence"][0]["url"] == fish["evidence"]["record_urls"][0]

        answer = client.post(
            path, json={"question": "What does it eat?", "aphia_id": fish["aphia_id"]}
        )
        assert answer.json()["evidence"] == []
        assert answer.json()["message"]
        assert client.post(path, json={"question": "Depth?", "aphia_id": 1}).status_code == 404

        for question, label in [
            ("What is the maximum depth?", "maximum depth"),
            ("How shallow can it be found?", "minimum depth"),
        ]:
            answer = client.post(path, json={"question": question, "aphia_id": fish["aphia_id"]})
            depths = [doc for doc in answer.json()["evidence"] if doc["topic"] == "depth"]
            assert len(depths) == 1
            assert label in depths[0]["text"]
            assert depths[0]["url"].startswith("https://www.fishbase.se/summary/")

        answer = client.post(
            path,
            json={"question": "What is the maximum depth of a whale shark?", "aphia_id": fish["aphia_id"]},
        )
        assert answer.json()["evidence"] == []

        exhibit = client.post(path, json={"question": "What animals are in the Open Sea exhibit?"})
        assert exhibit.json()["evidence"][0]["url"].endswith("/visit/exhibits/open-sea")


def test_guide_model_cannot_supply_new_citations(monkeypatch):
    monkeypatch.setenv("DIVEPOINT_GUIDE_API_KEY", "test-key")
    original_post = httpx.AsyncClient.post
    selected = "[1]"

    async def mock_post(self, url, *args, **kwargs):
        if url == "https://api.anthropic.com/v1/messages":
            assert "Blue rockfish" in kwargs["json"]["messages"][0]["content"]
            return httpx.Response(
                200,
                json={"content": [{"type": "text", "text": selected}]},
                request=httpx.Request("POST", url),
            )
        return await original_post(self, url, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)
    with TestClient(app) as client:
        dive = client.post("/v1/dives/plan", json={"text": "Monterey Bay"}).json()
        path = f"/v1/dives/{dive['id']}/ask"
        question = {"question": "What is the scientific name of Blue rockfish?"}
        answer = client.post(path, json=question).json()
        assert answer["mode"] == "rag"
        assert answer["evidence"][0]["url"].endswith("id=274823")

        selected = "[999]"
        assert client.post(path, json=question).status_code == 503
        selected = "[]"
        assert client.post(path, json=question).json()["evidence"] == []


@pytest.mark.parametrize(
    ("destination", "pack", "mrgid"),
    [("Red Sea", "red_sea", 4264), ("Raja Ampat", "raja_ampat", 21076)],
)
def test_bundled_reef_dive_works_with_public_services_offline(
    monkeypatch, destination, pack, mrgid
):
    async def reject_network(*args, **kwargs):
        pytest.fail("A bundled dive tried to call a public data service")

    with TestClient(app) as client:
        service = app.state.dives
        for provider in (service.marine, service.obis):
            monkeypatch.setattr(provider, "get", reject_network)

        response = client.post("/v1/dives/plan", json={"text": destination, "depth_m": 30})
        assert response.status_code == 200
        dive = response.json()
        assert dive["type"] in {"dive", "too_sparse"}
        assert dive["source_mode"] == "recorded"
        assert dive["place"]["mrgid"] == mrgid
        assert dive["captured_at"] == read_pack("provenance", pack)["captured_at"]
        assert dive["species"]
        qualified = {
            f"https://obis.org/occurrence/{row['id']}": row["speciesid"]
            for row in qualify(
                read_pack("occurrences", pack)["results"], dive["place"], dive["filters"]
            )
        }
        taxa = read_pack("taxa", pack)
        for species in dive["species"]:
            assert accepted_taxon(taxa[str(species["aphia_id"])])
            assert species["evidence"]["record_urls"]
            assert all(
                str(qualified[url]) == str(species["aphia_id"])
                for url in species["evidence"]["record_urls"]
            )

        species = dive["species"][0]
        card = client.get(f"/v1/species/{species['aphia_id']}?dive_id={dive['id']}")
        assert card.status_code == 200
        assert card.json()["evidence"]["record_urls"] == species["evidence"]["record_urls"]
        assert card.json()["taxonomy_url"].endswith(f"id={species['aphia_id']}")

        filtered = client.post(
            "/v1/dives/plan", json={"text": destination, "depth_m": 15, "month": 5}
        ).json()
        assert filtered["source_mode"] == "recorded"
        assert filtered["filters"] == {"depth_m": [0, 15], "months": [5]}
        assert all(s["depth_m"][1] <= 15 for s in filtered["species"])
