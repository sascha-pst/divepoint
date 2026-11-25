"""Extract seafloor grids from GEBCO 2026 using Rasterio (capture only)."""

import json
import math
from pathlib import Path

import rasterio
from rasterio.windows import Window

COG = (
    "https://data.source.coop/giswqs/gebco-bathymetry/"
    "gebco_2026_sub_ice_topo/gebco_2026_sub_ice.tif"
)
OUTPUT = Path(__file__).resolve().parents[1] / "src" / "terrain.json"
BOUNDS = {
    "red-sea": (42.29, 15.535, 42.456, 15.581),
    "raja-ampat": (130.685, -0.624, 130.86, -0.537),
}


def main():
    grids = {}
    with (
        rasterio.Env(
            GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
            CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
        ),
        rasterio.open(f"/vsicurl/{COG}") as grid,
    ):
        if grid.crs.to_epsg() != 4326 or not math.isclose(grid.res[0], 1 / 240):
            raise ValueError("Expected the 15-arc-second geographic GEBCO grid")
        for site, (west, south, east, north) in BOUNDS.items():
            top, left = grid.index(west, north)
            bottom, right = grid.index(east, south)
            samples = grid.read(
                1, window=Window(left, top, right - left + 1, bottom - top + 1), masked=True
            )
            if samples.mask.any() or (samples >= 0).any():
                raise ValueError(f"{site}: expected only submerged GEBCO cells")
            west_center, north_center = grid.xy(top, left)
            east_center, south_center = grid.xy(bottom, right)
            grids[site] = {
                "west": round(west_center, 8),
                "north": round(north_center, 8),
                "east": round(east_center, 8),
                "south": round(south_center, 8),
                "depthsM": (-samples).tolist(),
            }
    asset = {
        "source": {
            "label": "GEBCO 2026",
            "url": "https://doi.org/10.5285/4f68d5c7-45eb-f999-e063-7086abc036fa",
            "raster": COG,
            "resolutionArcSeconds": 15,
        },
        "grids": grids,
    }
    OUTPUT.write_text(json.dumps(asset, indent=2) + "\n")


if __name__ == "__main__":
    main()
