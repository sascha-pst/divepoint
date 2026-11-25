import asyncio
import hashlib
import json
from collections import Counter
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi import HTTPException

from app.cache.memory import MemoryCache
from app.checklist.manifest import build_species, qualify
from app.checklist.sources import dataset_credit, reviewed_occurrence
from app.clients.providers import MarineRegionsClient, OBISClient
from app.config import Settings
from app.place.parser import parse_request, season_months
from app.place.resolver import area_from_record

DATA = Path(__file__).parents[1] / "data"
PACK_ALIASES = {
    "monterey": ("monterey", "monterey bay", "monterey california", "monterey bay california"),
    "red_sea": ("red sea",),
    "raja_ampat": ("raja ampat", "raja ampat islands", "kepulauan raja ampat"),
}


def read_pack(name, pack="monterey"):
    return json.loads((DATA / pack / f"{name}.json").read_text())


class DiveService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()
        self.marine = MarineRegionsClient(settings=self.settings)
        self.obis = OBISClient(settings=self.settings)
        self.dives = MemoryCache()
        self.starter_packs = {}
        self.pack_aliases = {}
        self.fishbase = {}
        for pack, aliases in PACK_ALIASES.items():
            provenance = read_pack("provenance", pack)
            for filename, checksum in provenance["files"].items():
                if hashlib.sha256((DATA / pack / filename).read_bytes()).hexdigest() != checksum:
                    raise ValueError(f"Starter pack checksum mismatch: {pack}/{filename}")
            place = area_from_record(read_pack("place", pack))
            if place is None or place["geometry_wkt"] != provenance["geometry_wkt"]:
                raise ValueError(f"Starter pack area mismatch: {pack}")
            self.starter_packs[place["mrgid"]] = {
                "place": place,
                "occurrences": read_pack("occurrences", pack),
                "taxa": read_pack("taxa", pack),
                "photos": read_pack("photos", pack) if "photos.json" in provenance["files"] else {},
                "captured_at": provenance["captured_at"],
            }
            self.pack_aliases.update(dict.fromkeys(aliases, place["mrgid"]))
            self.fishbase.update(
                {f"{row['Genus']} {row['Species']}": row for row in read_pack("fishbase", pack)}
            )

    async def close(self):
        await asyncio.gather(self.marine.aclose(), self.obis.aclose())

    async def plan(self, request):
        try:
            parsed = parse_request(request.text, request.depth_m, request.month)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        starter = self.starter_packs.get(self.pack_aliases.get(parsed["place"]))
        if starter is not None:
            candidates = [starter["place"]]
        else:
            rows = await self.marine.search(parsed["place"])
            candidates = []
            for row in rows or []:
                area = area_from_record(row)
                if area and area["mrgid"] not in {entry["mrgid"] for entry in candidates}:
                    candidates.append(area)
            exact = [
                area for area in candidates if area["name"].casefold() == parsed["place"].casefold()
            ]
            candidates = (
                exact or sorted(candidates, key=lambda area: (len(area["name"]), area["name"]))[:8]
            )
        if not candidates:
            return {
                "type": "clarify",
                "candidates": [],
                "message": "No marine place matched. Try a named bay, sea, reef, or Monterey Bay.",
            }
        if request.place_id is not None:
            place = next((area for area in candidates if area["mrgid"] == request.place_id), None)
            if place is None:
                raise HTTPException(422, "Choose a place from the current search results.")
        elif len(candidates) > 1:
            return {
                "type": "clarify",
                "candidates": candidates,
                "message": "Which place did you mean?",
            }
        else:
            place = candidates[0]
        filters = {
            "depth_m": parsed["depth_m"],
            "months": parsed["months"] or season_months(parsed["season"], place["latitude"]),
        }
        if starter is not None:
            payload, taxa = starter["occurrences"], starter["taxa"]
        else:
            payload = await self.obis.get(
                "occurrence",
                {
                    "geometry": place["geometry_wkt"],
                    "startdepth": 0,
                    "enddepth": filters["depth_m"][1],
                    "startdate": f"{self.settings.earliest_record_year}-01-01",
                    "taxonid": 293496,
                    "absence": "false",
                    "dropped": "false",
                    "size": 1000,
                },
            )
        records = payload.get("results", [])
        reviewed = [row for row in records if reviewed_occurrence(row, recorded=starter is not None)]
        qualified = qualify(reviewed, place, filters, self.settings.earliest_record_year)
        if starter is None:
            ids = [
                str(key) for key, _ in Counter(row["speciesid"] for row in qualified).most_common(24)
            ]

            async def taxon(key):
                try:
                    response = await self.obis.get(f"taxon/{key}")
                    return key, next(iter(response.get("results", [])), {})
                except httpx.HTTPError:
                    return key, {}

            taxa = dict(await asyncio.gather(*(taxon(key) for key in ids)))
        species = build_species(qualified, taxa, self.fishbase, filters)
        manifest = {
            "id": str(uuid4()),
            "type": "dive" if len(species) >= 15 or request.allow_sparse else "too_sparse",
            "place": place,
            "filters": filters,
            "species": species,
            "source_mode": "recorded" if starter is not None else "live",
            "captured_at": starter["captured_at"] if starter is not None else None,
            "sample_size": len(records),
            "total_upstream_records": payload.get("total"),
            "message": f"{len(species)} verified fish species in this sample."
            if species
            else "No fish records passed the evidence and license checks. "
            "Try a starter dive, a deeper band, or all months.",
            "notice": "A bounded sample of OBIS records, not an exhaustive species list or an abundance estimate.",
        }
        if species:
            if len(self.dives._entries) >= 512:
                self.dives._entries.clear()
            self.dives.put(manifest["id"], manifest, 86400)
        return manifest

    def dive(self, dive_id):
        manifest = self.dives.get(dive_id)
        if manifest is None:
            raise HTTPException(404, "Dive expired or was not found. Plan a new dive.")
        return manifest

    def species_facts(self, species):
        row = self.fishbase.get(species["name"], {})
        facts = []
        if row:
            url = f"https://www.fishbase.se/summary/{row['SpecCode']}"
            for label, field, unit in [
                ("Maximum reported length", "Length", " cm"),
                ("Minimum depth", "DepthRangeShallow", " m"),
                ("Maximum depth", "DepthRangeDeep", " m"),
                ("Habitat", "DemersPelag", ""),
            ]:
                value = row.get(field)
                if value is not None:
                    suffix = (
                        f" ({row.get('LTypeMaxM') or 'type unspecified'})"
                        if field == "Length"
                        else ""
                    )
                    facts.append(
                        {
                            "label": label,
                            "value": f"{value}{unit}{suffix}",
                            "source_url": url,
                            "release": "v26.06",
                        }
                    )
        return facts

    async def card(self, dive_id, aphia_id):
        manifest = self.dive(dive_id)
        species = next((row for row in manifest["species"] if row["aphia_id"] == aphia_id), None)
        if species is None:
            raise HTTPException(404, "This species is not in the dive.")
        taxon_key = str(aphia_id)
        starter = (
            self.starter_packs[manifest["place"]["mrgid"]]
            if manifest["source_mode"] == "recorded"
            else None
        )
        photo_link = None
        photo_metadata = starter["photos"].get(taxon_key, {}) if starter else {}
        for taxon in photo_metadata.get("results", []):
            candidate = taxon.get("default_photo") or {}
            photo_id = candidate.get("id")
            if (
                taxon.get("name") == species["name"]
                and taxon.get("rank") == "species"
                and type(photo_id) is int
                and photo_id > 0
            ):
                photo_link = f"https://www.inaturalist.org/photos/{photo_id}"
                break
        dataset_ids = (url.rsplit("/", 1)[-1] for url in species["evidence"]["dataset_urls"])
        return {
            **species,
            "photo": None,
            "photo_link": photo_link,
            "dataset_credits": [dataset_credit(dataset_id) for dataset_id in dataset_ids],
            "facts": self.species_facts(species),
            "taxonomy_url": f"https://www.marinespecies.org/aphia.php?p=taxdetails&id={aphia_id}",
            "missing_facts": ["Diet", "Conservation status"],
            "place_name": manifest["place"]["name"],
        }
