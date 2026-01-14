"""
Minimal tests for geo_basic toolkit.

This file:
1) Mocks a Registrar to capture tools and call handlers (aligned with your example).
2) Registers the toolkit via setup(registrar).
3) Runs a few smoke tests for each tool to validate basic behavior.

Run:
  python -m tests.test_tool_geobasic
"""

import json
import math

# Import the toolkit setup and handlers indirectly by calling setup(registrar)
from terrabox.toolkits.geobasic import setup as geo_basic_setup

# -----------------------------
# Mock Registrar (compatible with your example)
# -----------------------------
class MockRegistrar:
    def __init__(self):
        self.toolkits = {}
        self.tools = {}          # slug -> spec
        self.handlers = {}       # slug -> handler

    def toolkit(self, name: str, description: str, version: str):
        self.toolkits[name] = {"description": description, "version": version}

    def tool(self, toolspec, handler):
        self.tools[toolspec.slug] = toolspec
        self.handlers[toolspec.slug] = handler

    # Convenience call method to simulate your platform's invocation
    def call(self, slug: str, arguments: dict, context: dict = None, account=None):
        if context is None:
            context = {}
        handler = self.handlers.get(slug)
        if not handler:
            raise KeyError(f"Tool not registered: {slug}")
        return handler(arguments, context, account)


# -----------------------------
# Helpers / sample inputs
# -----------------------------
SQUARE_POLY = {
    "type": "Polygon",
    "coordinates": [
        [
            [11.54, 48.14],
            [11.60, 48.14],
            [11.60, 48.18],
            [11.54, 48.18],
            [11.54, 48.14]
        ]
    ]
}

LINE = {
    "type": "LineString",
    "coordinates": [
        [11.54, 48.14],
        [11.60, 48.18],
        [11.62, 48.20]
    ]
}


# -----------------------------
# Smoke tests
# -----------------------------
def main():
    reg = MockRegistrar()
    geo_basic_setup(reg)

    # 1) AOI validate
    out = reg.call("geo_basic.aoi_validate", {"geojson": SQUARE_POLY}, context={"user_id": "u1"})
    assert out["geometry_type"] == "Polygon"
    assert "bbox" in out
    assert out["total_area_m2"] > 0
    print("aoi_validate OK:", out["bbox"], out["total_area_km2"])

    # 2) AOI area with GSD=10 m
    ar = reg.call("geo_basic.area", {"geojson": SQUARE_POLY, "gsd_m": 10})
    assert ar["area_m2"] > 0 and ar["pixel_estimate"] > 0
    print("area OK:", ar["area_km2"], "px_est:", int(ar["pixel_estimate"]))

    # 3) Distance
    dist = reg.call("geo_basic.distance", {
        "lon1": 11.54, "lat1": 48.14,
        "lon2": 11.60, "lat2": 48.18
    })
    assert dist["distance_m"] > 0
    print("distance OK:", round(dist["distance_m"], 1), "m")

    # 4) Pixel -> Area (10 m)
    pa = reg.call("geo_basic.pixel_area", {"pixels": 12345, "gsd_m": 10})
    assert math.isclose(pa["area_m2"], 12345 * 100, rel_tol=1e-9)
    print("pixel_area OK:", pa["area_m2"], "m²")

    # 5) Area -> Pixels (ceil)
    pf = reg.call("geo_basic.pixels_from_area", {"area_m2": 2500000, "gsd_m": 10, "rounding": "ceil"})
    assert pf["pixels_int"] >= 2500000 / 100
    print("pixels_from_area OK:", pf["pixels_int"], "px")

    # 6) Gridify (size mode, 100 m, centroid clipping ON)
    grid = reg.call("geo_basic.gridify", {"geojson": SQUARE_POLY, "mode": "size", "cell_width_m": 100, "clip": True})
    assert "features" in grid and len(grid["features"]) > 0
    print("gridify(size) OK: cells:", len(grid["features"]))

    # 7) Line length
    ll = reg.call("geo_basic.line_length", {"geojson": LINE})
    assert ll["length_m"] > 0
    print("line_length OK:", round(ll["length_m"], 1), "m")

    print("\nAll geo_basic smoke tests passed.")


if __name__ == "__main__":
    main()
