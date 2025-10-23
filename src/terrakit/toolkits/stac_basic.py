"""
stac_basic toolkit (rev2)
-------------------------
Unified data entry tools for STAC-compatible EO data sources:

1) stac_basic.search
   - Query a STAC API (pystac-client) with spatial/temporal/prop filters.
   - Optional Planetary Computer asset signing (if 'planetary_computer' is available).

2) stac_basic.stack
   - Stack STAC Items into a lazy xarray.DataArray via stackstac.
   - Optional export:
       - Zarr (multi-time friendly)
       - COG (single time slice; requires rioxarray + GDAL stack)

Notes:
- Lazy imports allow this module to be imported even if optional deps are missing.
- The interface is minimal and robust; ideal as a building block for pipelines.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Union
import os
import json

from ..core.tool_registry import ToolSpec

# ---------------------------------------------------------------------
# Lazy import flags and handles
# ---------------------------------------------------------------------
_HAS_PYSTAC = False
_HAS_STACKSTAC = False
_HAS_PC = False
_HAS_RIOXARRAY = False
Client = None
stack = None
pc = None


def _lazy_imports():
    """Import optional libraries only when handlers are invoked."""
    global _HAS_PYSTAC, _HAS_STACKSTAC, _HAS_PC, _HAS_RIOXARRAY, Client, stack, pc
    if not _HAS_PYSTAC:
        try:
            from pystac_client import Client as _Client  # type: ignore
            Client = _Client
            _HAS_PYSTAC = True
        except Exception as e:
            raise ImportError("pystac-client is required. Install with: pip install pystac-client") from e

    if not _HAS_STACKSTAC:
        try:
            from stackstac import stack as _stack  # type: ignore
            stack = _stack
            _HAS_STACKSTAC = True
        except Exception as e:
            raise ImportError("stackstac is required. Install with: pip install stackstac") from e

    if not _HAS_PC:
        try:
            import planetary_computer as _pc  # type: ignore
            pc = _pc
            _HAS_PC = True
        except Exception:
            _HAS_PC = False
            pc = None

    if not _HAS_RIOXARRAY:
        try:
            import rioxarray  # noqa: F401
            _HAS_RIOXARRAY = True
        except Exception:
            _HAS_RIOXARRAY = False


# ---------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------
def _norm_aoi_geojson(geojson_like: Union[str, Dict[str, Any], None]) -> Optional[Dict[str, Any]]:
    """Accept GeoJSON string/dict/None; return dict or None."""
    if geojson_like is None:
        return None
    if isinstance(geojson_like, str):
        return json.loads(geojson_like)
    if isinstance(geojson_like, dict):
        return geojson_like
    raise ValueError("AOI must be a GeoJSON string or dict (or None).")


def _items_to_minimal(items, asset_keys: Optional[List[str]] = None, max_assets_per_item: int = 50):
    """
    Convert pystac.ItemCollection (or list of Items/dicts) into a minimal, JSON-safe structure.
    Keeps: id, collection, datetime, and selected assets {key: {href, type}}.
    """
    out = []
    for it in items:
        # Support both pystac.Item and plain dict
        it_id = getattr(it, "id", None) or (it.get("id") if isinstance(it, dict) else None)
        it_coll = getattr(it, "collection_id", None) or (it.get("collection") if isinstance(it, dict) else None)
        dt_attr = getattr(it, "datetime", None)
        if dt_attr is not None:
            it_dt = dt_attr.isoformat()
        else:
            props = it.get("properties", {}) if isinstance(it, dict) else {}
            it_dt = props.get("datetime")
        assets = getattr(it, "assets", None) or (it.get("assets") if isinstance(it, dict) else {}) or {}

        rec = {"id": it_id, "collection": it_coll, "datetime": it_dt, "assets": {}}
        cnt = 0
        for k, a in assets.items():
            if asset_keys and k not in asset_keys:
                continue
            href = getattr(a, "href", None) or (a.get("href") if isinstance(a, dict) else None)
            media_type = getattr(a, "media_type", None) or (a.get("type") if isinstance(a, dict) else None)
            rec["assets"][k] = {"href": href, "type": media_type}
            cnt += 1
            if cnt >= max_assets_per_item:
                break
        out.append(rec)
    return out


# ---------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------
def stac_search_handler(arguments: dict, context: dict, account=None) -> Dict[str, Any]:
    """
    Search a STAC API endpoint using pystac-client.

    Parameters:
      - endpoint: str, STAC API URL (e.g., MPC: https://planetarycomputer.microsoft.com/api/stac/v1)
      - collections: list[str], required
      - datetime: str (ISO or interval 'start/end'), optional
      - aoi: GeoJSON (dict or JSON string) or bbox: [minx,miny,maxx,maxy]
      - query: dict, STAC query filters (e.g., {"eo:cloud_cover":{"lt":20}})
      - limit: int, server-side page size (default 100)
      - max_items: int, client-side cap (default 100)
      - asset_keys: list[str], filter returned assets to these keys
      - sign: bool, if True and endpoint is MPC, sign the assets (requires planetary-computer)

    Returns:
      - items_minimal: [{id, collection, datetime, assets{key:{href,type}}}, ...]
      - matched: server-reported matched count if available
    """
    _lazy_imports()

    endpoint = arguments.get("endpoint")
    if not endpoint:
        raise ValueError("Missing 'endpoint'")

    collections = arguments.get("collections") or []
    if not isinstance(collections, list) or not collections:
        raise ValueError("'collections' must be a non-empty list")

    dt = arguments.get("datetime")
    bbox = arguments.get("bbox")
    aoi = _norm_aoi_geojson(arguments.get("aoi"))
    query = arguments.get("query") or None
    limit = int(arguments.get("limit", 100))
    max_items = int(arguments.get("max_items", 100))
    asset_keys = arguments.get("asset_keys") or None
    sign = bool(arguments.get("sign", False))

    if sign and _HAS_PC:
        client = Client.open(endpoint, modifier=pc.sign)  # type: ignore
    else:
        client = Client.open(endpoint)

    search_kwargs: Dict[str, Any] = {
        "collections": collections,
        "max_items": max_items,
    }
    if dt:
        search_kwargs["datetime"] = dt
    if bbox:
        search_kwargs["bbox"] = bbox
    if aoi:
        search_kwargs["intersects"] = aoi.get("geometry", aoi)
    if query:
        search_kwargs["query"] = query
    if limit:
        search_kwargs["limit"] = limit

    search = client.search(**search_kwargs)
    item_collection = search.item_collection()
    items = list(item_collection)

    minimal = _items_to_minimal(items, asset_keys=asset_keys)
    # Ensure 'matched' is a JSON-serializable value
    matched_val = None
    try:
        m = getattr(search, "matched", None)
        matched_val = m() if callable(m) else m
    except Exception:
        matched_val = None

    if matched_val is None:
        try:
            m2 = getattr(item_collection, "matched", None)
            matched_val = m2() if callable(m2) else m2
        except Exception:
            matched_val = None

    return {
        "items_minimal": minimal,
        "matched": matched_val
    }


def stac_stack_handler(arguments: dict, context: dict, account=None) -> Dict[str, Any]:
    """
    Stack STAC Items into a lazy xarray.DataArray via stackstac, with optional export.

    Items source (provide one):
      - items: list of minimal dicts (as returned by stac_basic.search)
      - item_hrefs: list[str] of item JSON URLs/paths (requires online or local files)
      - search: dict of arguments to pass into stac_basic.search to fetch items

    Options:
      - assets: list[str], which asset keys/bands to load (e.g., ["B04","B08"])
      - resolution: number, target pixel size (units depend on target CRS)
      - crs: "EPSG:xxxx", target CRS string
      - bounds: [minx,miny,maxx,maxy] or
      - aoi: GeoJSON (will be converted to geometry)
      - chunks: dict, e.g., {"time":1,"band":1,"y":1024,"x":1024}
      - resampling: "nearest" | "bilinear"
      - dtype: str, cast to dtype (e.g., "float32")
      - save: {"type":"zarr","path":"out.zarr"} or {"type":"cog","path":"out.tif"}

    Returns:
      - info: {"dims":..., "coords":[...], "crs":..., "resolution":..., "chunks":...}
      - saved: absolute path to export if performed, else None
    """
    _lazy_imports()

    # Resolve items
    items_min = arguments.get("items")
    item_hrefs = arguments.get("item_hrefs")
    search_args = arguments.get("search")

    if items_min:
        items = items_min
    elif item_hrefs:
        from pystac import Item  # type: ignore
        items = [Item.from_file(href) for href in item_hrefs]
    elif search_args:
        res = stac_search_handler(search_args, context, account)
        items = res["items_minimal"]
    else:
        raise ValueError("Provide one of: 'items', 'item_hrefs', or 'search'")

    # Stack options
    assets = arguments.get("assets")
    resolution = arguments.get("resolution")
    crs = arguments.get("crs")
    bounds = arguments.get("bounds")
    aoi = arguments.get("aoi")
    chunks = arguments.get("chunks") or {"time": 1, "band": 1, "y": 1024, "x": 1024}
    resampling = arguments.get("resampling", "nearest")
    dtype = arguments.get("dtype")

    # Geometry/bounds for stackstac
    bounds_geom = None
    if aoi:
        gj = _norm_aoi_geojson(aoi)
        bounds_geom = gj.get("geometry", gj)
    elif bounds:
        bounds_geom = bounds

    # Build lazy DataArray
    da = stack(
        items,
        assets=assets,
        resolution=resolution,
        bounds=bounds_geom,
        epsg=crs.split(":")[1] if crs and crs.startswith("EPSG:") else None,
        chunks=chunks,
        resampling=resampling
    )

    if dtype:
        da = da.astype(dtype)

    # ----- Robust CRS summary (rio -> attrs['crs'] -> input arg) -----
    crs_summary = None
    try:
        if hasattr(da, "rio") and getattr(da.rio, "crs", None) is not None:
            crs_summary = str(da.rio.crs)
    except Exception:
        crs_summary = None
    
    # Check for mock rio in attrs (for testing)
    if not crs_summary:
        mock_rio = getattr(da, "attrs", {}).get("_rio_mock")
        if mock_rio and hasattr(mock_rio, "crs") and mock_rio.crs:
            crs_summary = str(mock_rio.crs)
    
    if not crs_summary:
        crs_summary = getattr(da, "attrs", {}).get("crs") or crs

    # ----- Robust chunks summary (works with and without dask) -----
    chunks_summary = None
    # xarray exposes "chunks" (deprecated) or "chunksizes" (preferred)
    if hasattr(da, "chunksizes") and getattr(da, "chunksizes"):
        chunks_summary = {k: tuple(v) for k, v in da.chunksizes.items()}
    elif hasattr(da, "chunks") and getattr(da, "chunks"):
        # 'chunks' might be a tuple-of-tuples in older versions
        try:
            chunks_summary = {k: tuple(v) for k, v in da.chunks.items()}  # type: ignore
        except Exception:
            chunks_summary = None

    info = {
        "dims": {k: int(v) for k, v in da.sizes.items()},
        "coords": list(da.coords),
        "crs": crs_summary,
        "resolution": resolution,
        "chunks": chunks_summary,
    }

    # ----- Optional export -----
    saved = None
    save = arguments.get("save")
    if save:
        save_type = (save.get("type") or "").lower()
        save_path = save.get("path")
        if not save_path:
            raise ValueError("When passing 'save', provide a 'path'.")

        if save_type == "zarr":
            # Clean attrs to remove non-serializable objects before saving
            da_clean = da.copy()
            if "_rio_mock" in da_clean.attrs:
                del da_clean.attrs["_rio_mock"]
            ds = da_clean.to_dataset(name="data")
            ds.to_zarr(save_path, mode="w")
            saved = os.path.abspath(save_path)

        elif save_type == "cog":
            if not _HAS_RIOXARRAY:
                raise ImportError("COG export requires rioxarray. Install with: pip install rioxarray")
            if "time" not in da.dims or int(da.sizes["time"]) != 1:
                raise ValueError("COG export requires a single time slice (time dimension length == 1).")
            da0 = da.isel(time=0)
            da0.rio.to_raster(save_path)
            saved = os.path.abspath(save_path)

        else:
            raise ValueError("Unknown save.type. Use 'zarr' or 'cog'.")

    return {"info": info, "saved": saved}


# ---------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------
def setup(registrar):
    """Register the stac_basic toolkit and tools."""
    registrar.toolkit(
        name="stac_basic",
        description="STAC data entry: search (pystac-client) and stack (stackstac) with optional exports.",
        version="0.2.0"
    )

    # stac.search
    registrar.tool(
        ToolSpec(
            slug="stac_basic.search",
            name="STAC Search",
            description="Search a STAC API with spatial/temporal filters; optional MPC asset signing.",
            parameters={
                "type": "object",
                "properties": {
                    "endpoint": {"type": "string", "description": "STAC API endpoint URL"},
                    "collections": {"type": "array", "items": {"type": "string"}},
                    "datetime": {"type": "string", "description": "ISO or interval (e.g., 2024-01-01/2024-01-31)"},
                    "bbox": {"type": "array", "items": {"type": "number"}, "description": "BBox [minx,miny,maxx,maxy]"},
                    "aoi": {"description": "GeoJSON dict or string (Feature/Geometry)"},
                    "query": {"type": "object", "description": "STAC property filter"},
                    "limit": {"type": "integer", "default": 100},
                    "max_items": {"type": "integer", "default": 100},
                    "asset_keys": {"type": "array", "items": {"type": "string"}},
                    "sign": {"type": "boolean", "default": False}
                },
                "required": ["endpoint", "collections"]
            },
            requires_connection=False
        ),
        stac_search_handler
    )

    # stac.stack
    registrar.tool(
        ToolSpec(
            slug="stac_basic.stack",
            name="STAC Stack",
            description="Build a lazy xarray DataArray with stackstac; optionally export to Zarr/COG.",
            parameters={
                "type": "object",
                "properties": {
                    "items": {"description": "Items from stac_basic.search (list of minimal dicts)"},
                    "item_hrefs": {"type": "array", "items": {"type": "string"}},
                    "search": {"type": "object", "description": "Arguments for stac_basic.search"},
                    "assets": {"type": "array", "items": {"type": "string"}},
                    "resolution": {"description": "Target pixel size (units depend on CRS)"},
                    "crs": {"type": "string", "description": "Target CRS (e.g., 'EPSG:3857')"},
                    "bounds": {"type": "array", "items": {"type": "number"}},
                    "aoi": {"description": "GeoJSON dict or string for cropping"},
                    "chunks": {"type": "object"},
                    "resampling": {"type": "string", "enum": ["nearest", "bilinear"], "default": "nearest"},
                    "dtype": {"type": "string"},
                    "save": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "enum": ["zarr", "cog"]},
                            "path": {"type": "string"}
                        }
                    }
                },
                "required": []
            },
            requires_connection=False
        ),
        stac_stack_handler
    )
