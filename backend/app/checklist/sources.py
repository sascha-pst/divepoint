"""Reviewed OBIS datasets for the public noncommercial demo."""

CC_BY = "https://creativecommons.org/licenses/by/4.0/"
CC0 = "https://creativecommons.org/publicdomain/zero/1.0/"

# Dataset pages list the original provider, full citation and applicable license.
OBIS_DATASETS = {
    "730e0918-43bb-496a-8126-f3a5849316fe": ("PISCO Kelp Forest Community Surveys", CC_BY),
    "a6155d3d-48b8-4778-83aa-776b459a75d1": (
        "MLPA Marine Protected Area Network kelp forest monitoring",
        CC_BY,
    ),
    "5b6251f6-a7a5-4dc9-994d-c9504b54776f": (
        "NOAA Rockfish Recruitment and Ecosystem Assessment Survey",
        CC0,
    ),
    "cfceb150-bbe2-4efb-8682-14cfc7167e7c": ("Reef Check California rocky reef surveys", CC0),
    "f8c046f0-e8ae-49f5-b94c-f78809a8b7dc": ("Western Australian Museum Fish Collection", CC_BY),
    "10b213e6-a9c4-459e-a40c-ef9edc461b97": ("Bernice P. Bishop Museum marine data", CC0),
    "04e3fd32-b08b-4806-a016-d2dff52ae55a": ("Asia-Pacific Dataset", CC_BY),
    "fbe20230-f4f1-48e7-83ee-4cd3ad15a1db": (
        "South African Institute for Aquatic Biodiversity fish collection",
        CC_BY,
    ),
    "340cf56f-f494-48c1-9f13-dd1fb3bfbdf2": (
        "National Museum of Nature and Science fish collection",
        CC_BY,
    ),
    "a4257cff-3c2c-4a60-ab29-91f65545bb08": ("IndOBIS Dataset (93630–103790)", CC_BY),
}


def reviewed_occurrence(row, *, recorded):
    dataset_id = row.get("dataset_id")
    dataset = OBIS_DATASETS.get(dataset_id)
    if dataset is None:
        return False
    license_text = row.get("license")
    if license_text in (None, ""):
        return True  # The exact dataset's published license fills an omitted field.
    if not isinstance(license_text, str):
        return False
    license_text = license_text.strip().lower().removeprefix("https://").removeprefix("http://")
    license_text = license_text.removeprefix("www.").rstrip("/").removesuffix("/legalcode")
    if dataset[1] == CC_BY:
        return license_text in {"ccby", "cc-by", "creativecommons.org/licenses/by/4.0"}
    if license_text in {"cc0", "creativecommons.org/publicdomain/zero/1.0"}:
        return True
    # The checked-in NOAA rows carry a legacy redistribution and warranty notice.
    return (
        recorded
        and dataset_id == "5b6251f6-a7a5-4dc9-994d-c9504b54776f"
        and license_text.startswith("the data may be used and redistributed for free")
    )


def dataset_credit(dataset_id):
    title, license_url = OBIS_DATASETS[dataset_id]
    return {
        "title": title,
        "source_url": f"https://obis.org/dataset/{dataset_id}",
        "license": "CC BY 4.0" if license_url == CC_BY else "CC0 1.0",
        "license_url": license_url,
    }
