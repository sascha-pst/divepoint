"""Export the recorded, license-filtered game responses for static hosting."""

import asyncio
import json
from pathlib import Path

from app.api.dives import PlanRequest
from app.checklist.service import DiveService


async def main():
    output = Path(__file__).resolve().parents[1] / "dist" / "dives"
    output.mkdir(parents=True, exist_ok=True)
    service = DiveService()
    try:
        for place in ("Monterey Bay", "Red Sea", "Raja Ampat"):
            slug = place.lower().replace(" ", "-")
            for depth in (15, 30, 60):
                for month in range(13):
                    key = f"{slug}-{depth}-{month}"
                    manifest = await service.plan(
                        PlanRequest(text=place, depth_m=depth, month=month or None)
                    )
                    if manifest.get("source_mode") != "recorded":
                        raise ValueError(f"{key} did not resolve to a recorded dive")
                    cards = {
                        fish["aphia_id"]: await service.card(manifest["id"], fish["aphia_id"])
                        for fish in manifest["species"]
                    }
                    manifest["id"] = key
                    (output / f"{key}.json").write_text(
                        json.dumps({"manifest": manifest, "cards": cards}, separators=(",", ":"))
                    )
    finally:
        await service.close()


if __name__ == "__main__":
    asyncio.run(main())
