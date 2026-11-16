import copy
import json
import shutil
from pathlib import Path

import pytest

from app.fishbase.loader import accepted_taxa, load_snapshot, prepare_publications

RECORDED = Path(__file__).parents[1] / "fixtures/recorded"
SNAPSHOT = RECORDED / "fishbase/v26.06"


@pytest.fixture
def snapshot():
    return load_snapshot(SNAPSHOT, "v26.06")


@pytest.fixture
def taxa():
    return accepted_taxa([RECORDED / "worms.json"])


def test_real_snapshot_maps_only_verified_species(snapshot, taxa):
    publications = prepare_publications(snapshot, taxa)
    assert len(publications) == 1
    species = publications[0].species
    assert species["aphia_id"] == 274772
    assert species["fishbase_spec_code"] == 3950
    assert species["scientific_name"] == "Sebastes atrovirens"
    assert species["depth_min"] == 9
    assert species["depth_max"] == 46
    assert species["max_length_cm"] == 42
    assert len(snapshot.tables["species"]) == 3  # Two freshwater taxa remain raw, unmapped.
    assert all(
        doc["release_version"] == "v26.06" and doc["url"].endswith("/3950")
        for doc in publications[0].documents
    )
    assert any("TL" in doc["text"] for doc in publications[0].documents)
    assert publications[0].documents == prepare_publications(snapshot, taxa)[0].documents


def test_no_mapping_never_fabricates_aphia_ids(snapshot):
    assert prepare_publications(snapshot, {}) == []


def test_tampered_snapshot_fails_before_import(tmp_path):
    directory = tmp_path / "snapshot"
    shutil.copytree(SNAPSHOT, directory)
    with (directory / "species.parquet").open("ab") as file:
        file.write(b"corruption")
    with pytest.raises(ValueError, match="checksum"):
        load_snapshot(directory, "v26.06")


def test_wrong_release_is_rejected():
    with pytest.raises(ValueError, match="provenance"):
        load_snapshot(SNAPSHOT, "v24.07")


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "unaccepted"},
        {"rank": "Genus"},
        {"isMarine": 0},
        {"valid_AphiaID": 123},
        {"AphiaID": 0, "valid_AphiaID": 0},
    ],
)
def test_unsafe_taxonomy_is_not_published(changes, tmp_path):
    record = json.loads((RECORDED / "worms.json").read_text())[0]
    record.update(changes)
    path = tmp_path / "worms.json"
    path.write_text(json.dumps([record]))
    assert accepted_taxa([path]) == {}


def test_missing_and_conflicting_values_stay_unknown(snapshot, taxa):
    snapshot = copy.deepcopy(snapshot)
    species = next(row for row in snapshot.tables["species"] if row["SpecCode"] == 3950)
    species.update(Length=None, LengthFemale=None, DepthRangeShallow=None, DepthRangeDeep=None)
    morphs = [row for row in snapshot.tables["morphdat"] if row["Speccode"] == 3950]
    assert morphs
    morphs[0]["CShape"] = "test-conflict-one"
    conflicting = dict(morphs[0], CShape="test-conflict-two")
    snapshot.tables["morphdat"].append(conflicting)
    result = prepare_publications(snapshot, taxa)[0]
    assert result.species["max_length_cm"] is None
    assert result.species["depth_min"] is None
    assert result.species["tail_shape"] is None
    assert not any(
        doc["field"] in {"Length", "LengthFemale", "depth_min", "depth_max", "tail_shape"}
        for doc in result.documents
    )


def test_female_length_is_included_without_losing_measurement_type(snapshot, taxa):
    species = next(row for row in snapshot.tables["species"] if row["SpecCode"] == 3950)
    species.update(LengthFemale=50, LTypeMaxF="SL")
    result = prepare_publications(snapshot, taxa)[0]
    assert result.species["max_length_cm"] == 50
    assert any(doc["field"] == "LengthFemale" and "(SL)" in doc["text"] for doc in result.documents)


def test_inverted_depth_range_is_rejected(snapshot, taxa):
    species = next(row for row in snapshot.tables["species"] if row["SpecCode"] == 3950)
    species.update(DepthRangeShallow=100, DepthRangeDeep=10)
    with pytest.raises(ValueError, match="inverted"):
        prepare_publications(snapshot, taxa)


def test_upstream_zero_placeholder_is_not_published(snapshot, taxa):
    snapshot.tables["species"].append({"SpecCode": 0})
    assert len(prepare_publications(snapshot, taxa)) == 1
