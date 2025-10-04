"""
Minimal tests for stac_basic toolkit using in-memory stubs.

What this test does:
1) Injects small stubs for 'pystac-client' and 'stackstac' so we can run offline.
2) Mocks a Registrar compatible with your example.
3) Calls stac_basic.search and stac_basic.stack, including a Zarr-like export path.

Run:
  python -m tests.test_stac_basic
"""

import os
import sys
import types
import json
import numpy as np
import xarray as xr

# ------------------------------------------------------------------------------
# 1) Stubs for pystac-client and stackstac (comment out if using real packages)
# ------------------------------------------------------------------------------

# pystac-client stub
if "pystac_client" not in sys.modules:
    pc_mod = types.ModuleType("pystac_client")

    class _ItemAsset:
        def __init__(self, href, media_type="image/tiff; application=geotiff"):
            self.href = href
            self.media_type = media_type

    class _Item:
        def __init__(self, id_, collection_id, dt_iso, assets):
            self.id = id_
            self.collection_id = collection_id
            import datetime as dt
            self.datetime = dt.datetime.fromisoformat(dt_iso.replace("Z", "+00:00"))
            self.assets = {k: _ItemAsset(v) for k, v in assets.items()}

    class _ItemCollection(list):
        matched = 2

    class _Search:
        matched = 2
        def __init__(self, items):
            self._items = items
        def item_collection(self):
            ic = _ItemCollection()
            ic.extend(self._items)
            return ic

    class _Client:
        def __init__(self, endpoint, modifier=None):
            self.endpoint = endpoint
            self.modifier = modifier
        @classmethod
        def open(cls, endpoint, modifier=None):
            return cls(endpoint, modifier=modifier)
        def search(self, **kwargs):
            # Return two fake items with assets keys ["B04","B08"]
            items = [
                _Item("itemA", kwargs["collections"][0], "2024-01-10T00:00:00Z",
                      {"B04": "s3://bucket/A_B04.tif", "B08": "s3://bucket/A_B08.tif"}),
                _Item("itemB", kwargs["collections"][0], "2024-01-20T00:00:00Z",
                      {"B04": "s3://bucket/B_B04.tif", "B08": "s3://bucket/B_B08.tif"}),
            ]
            return _Search(items)

    pc_mod.Client = _Client
    sys.modules["pystac_client"] = pc_mod

# stackstac stub
if "stackstac" not in sys.modules:
    ss_mod = types.ModuleType("stackstac")

    def _stack(items, assets=None, resolution=None, bounds=None, epsg=None, chunks=None, resampling="nearest"):
        """
        Build a tiny synthetic DataArray with dims (time, band, y, x).
        This mimics stackstac API shape/coords but uses random data.
        """
        ntime = len(items)
        bands = assets or ["B04", "B08"]
        nband = len(bands)
        # Tiny spatial grid
        ny, nx = 16, 16
        data = np.random.rand(ntime, nband, ny, nx).astype("float32")
        time = np.array([f"2024-01-{10+idx:02d}" for idx in range(ntime)], dtype="datetime64[D]")
        da = xr.DataArray(
            data,
            dims=("time", "band", "y", "x"),
            coords={"time": time, "band": bands, "y": np.arange(ny), "x": np.arange(nx)},
            name="data"
        )
        # add a tiny rioxarray-like attribute for CRS in summary (not writing rasters here)
        # Instead of setting da.rio directly, we'll use attrs to store CRS info
        if epsg:
            da.attrs["crs"] = f"EPSG:{epsg}"
        
        # Create a mock rio accessor that can be accessed
        class _RIO:
            def __init__(self, crs=None):
                self.crs = crs
        
        # Store the rio-like object in attrs for later access
        da.attrs["_rio_mock"] = _RIO(f"EPSG:{epsg}" if epsg else None)
        return da

    ss_mod.stack = _stack
    sys.modules["stackstac"] = ss_mod


# ------------------------------------------------------------------------------
# 2) Mock Registrar (same shape as your example)
# ------------------------------------------------------------------------------
class MockRegistrar:
    def __init__(self):
        self.toolkits = {}
        self.tools = {}
        self.handlers = {}
    def toolkit(self, name: str, description: str, version: str):
        self.toolkits[name] = {"description": description, "version": version}
    def tool(self, toolspec, handler):
        self.tools[toolspec.slug] = toolspec
        self.handlers[toolspec.slug] = handler
    def call(self, slug: str, arguments: dict, context: dict = None, account=None):
        if context is None:
            context = {}
        h = self.handlers.get(slug)
        if not h:
            raise KeyError(f"Tool not registered: {slug}")
        return h(arguments, context, account)


# ------------------------------------------------------------------------------
# 3) Import toolkit and perform smoke tests
# ------------------------------------------------------------------------------
from src.terralink_platform.toolkits.stac_basic import setup as stac_setup

def main():
    reg = MockRegistrar()
    stac_setup(reg)

    # 搜索（S2 L2A，限定时间/区域并筛波段）
    # Note: bbox 或 aoi 必须提供一个
    minx, miny, maxx, maxy = 114.05, 22.54, 114.07, 22.56
    sr = reg.call("stac_basic.search", {
        "endpoint": "https://earth-search.aws.element84.com/v1",
        "collections": ["sentinel-2-l2a"],
        "datetime": "2024-06-01/2024-06-30",
        "bbox": [minx, miny, maxx, maxy],        # 或 aoi: your_geojson
        "query": {"eo:cloud_cover": {"lt": 20}}, # 可选：云量过滤
        "asset_keys": ["B04", "B08"],
        "limit": 50, "max_items": 50
    })
    # 堆栈（10 m 到 WebMercator；懒加载，可后续导出）
    st = reg.call("stac_basic.stack", {
        "items": sr["items_minimal"],
        "assets": ["B04", "B08"],
        "resolution": 10,
        "crs": "EPSG:3857",
        "chunks": {"time": 1, "band": 1, "y": 1024, "x": 1024},
        "save": {"type": "zarr", "path": "out.zarr"}
    })

    assert "info" in st and st["info"]["dims"]["time"] == 2
    # Zarr writing in stub is simulated by xarray (local dir). Check dir created.
    assert os.path.isdir("out.zarr")
    print("stac_basic.stack OK: dims =", st["info"]["dims"], "saved =", st["saved"])

    print("\nAll stac_basic smoke tests passed.")

if __name__ == "__main__":
    main()
