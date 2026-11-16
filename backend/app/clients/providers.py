from typing import Any
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict

from app.clients.base import PublicDataClient


class Taxon(BaseModel):
    model_config = ConfigDict(extra="ignore")
    AphiaID: int
    scientificname: str
    rank: str | None = None
    valid_AphiaID: int | None = None


class LicensedPhoto(BaseModel):
    url: str
    license_code: str
    attribution: str
    photo_page_url: str


class MarineRegionsClient(PublicDataClient):
    def __init__(self, **kwargs):
        super().__init__("https://www.marineregions.org/rest/", **kwargs)

    async def search(self, name: str) -> list[dict[str, Any]]:
        return await self.get(
            f"getGazetteerRecordsByName.json/{quote(name, safe='')}/",
            {"like": "true", "fuzzy": "true"},
        )


class OBISClient(PublicDataClient):
    def __init__(self, **kwargs):
        super().__init__("https://api.obis.org/v3/", **kwargs)

    async def checklist(
        self, geometry_wkt: str, depth: tuple[float, float], earliest_year: int = 1970
    ) -> dict[str, Any]:
        # Aggregate checklist is discovery only. Validate individual occurrence evidence in M2.
        return await self.get(
            "checklist",
            {
                "geometry": geometry_wkt,
                "startdepth": depth[0],
                "enddepth": depth[1],
                "startdate": f"{earliest_year}-01-01",
            },
        )


class GBIFClient(PublicDataClient):
    def __init__(self, **kwargs):
        super().__init__("https://api.gbif.org/v1/", **kwargs)

    async def species_counts(self, geometry_wkt: str, earliest_year: int = 1970) -> dict[str, Any]:
        # Facets are discovery only: pagination, marine/depth checks and synonym mapping are M2.
        return await self.get(
            "occurrence/search",
            {
                "geometry": geometry_wkt,
                "facet": "speciesKey",
                "facetLimit": 1000,
                "limit": 0,
                "hasCoordinate": "true",
                "hasGeospatialIssue": "false",
                "occurrenceStatus": "PRESENT",
                "year": f"{earliest_year},2100",
            },
        )


class WoRMSClient(PublicDataClient):
    def __init__(self, **kwargs):
        super().__init__("https://www.marinespecies.org/rest/", **kwargs)

    async def taxon(self, aphia_id: int) -> Taxon:
        return Taxon.model_validate(await self.get(f"AphiaRecordByAphiaID/{aphia_id}"))

    async def search(self, name: str) -> list[Taxon]:
        rows = await self.get(
            f"AphiaRecordsByName/{quote(name, safe='')}", {"marine_only": "true", "like": "false"}
        )
        return [Taxon.model_validate(row) for row in rows]


class INaturalistClient(PublicDataClient):
    ALLOWED_LICENSES = frozenset({"cc0", "cc-by", "cc-by-sa"})

    def __init__(self, **kwargs):
        super().__init__("https://api.inaturalist.org/v1/", **kwargs)

    async def photo(self, taxon_id: int) -> LicensedPhoto | None:
        payload = await self.get(f"taxa/{taxon_id}")
        for taxon in payload.get("results", []):
            photo = taxon.get("default_photo") or {}
            if (
                photo.get("license_code") in self.ALLOWED_LICENSES
                and photo.get("attribution")
                and photo.get("url")
                and photo.get("id")
            ):
                return LicensedPhoto(
                    url=photo["url"],
                    license_code=photo["license_code"],
                    attribution=photo["attribution"],
                    photo_page_url=f"https://www.inaturalist.org/photos/{photo['id']}",
                )
        return None
