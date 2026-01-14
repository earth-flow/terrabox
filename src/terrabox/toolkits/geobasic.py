"""
Geo Basic Toolkit (production-ready, no heavy deps required).

This toolkit provides small, reusable geospatial utilities that are useful
for many EO/urban demos and workflows:

1) geo_basic.aoi_validate    - Validate/normalize an AOI GeoJSON and compute bbox/centroid/area/perimeter
2) geo_basic.area            - Compute AOI area (m², km²); optionally estimate pixel count by GSD
3) geo_basic.distance        - Geodesic distance between two lon/lat points
4) geo_basic.pixel_area      - Convert pixel count + GSD -> area
5) geo_basic.pixels_from_area- Convert area + GSD -> pixel count (with rounding)
6) geo_basic.gridify         - Create a regular grid over AOI (by size in meters or rows/cols), optional centroid-in-AOI clipping
7) geo_basic.line_length     - Geodesic length of LineString/MultiLineString

Notes:
- Coordinates are expected in WGS84 (EPSG:4326).
- If 'pyproj' is installed, geodesic areas/lengths use accurate ellipsoidal math.
  Otherwise, robust approximations are used (clearly documented below).
"""

from typing import Any, Dict, Tuple, List, Union, Optional
import json
import math

# Import ToolSpec from your platform core (same style as your example)
from ..core.registry import ToolSpec

# Optional dependency for accurate ellipsoidal area/length
try:
    from pyproj import Geod
    _GEOD = Geod(ellps="WGS84")
except Exception:
    _GEOD = None


# -------------------------------------------------------------------
# Internal helpers (pure-Python, zero external deps)
# -------------------------------------------------------------------
def _ensure_geojson_obj(geojson_like: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Ensure input is a GeoJSON dict (accept JSON string or dict)."""
    if isinstance(geojson_like, str):
        try:
            return json.loads(geojson_like)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid GeoJSON string: {e}")
    elif isinstance(geojson_like, dict):
        return geojson_like
    else:
        raise ValueError("`geojson` must be a dict or JSON string")


def _extract_coords(geom: Dict[str, Any]) -> List:
    """Return 'coordinates' from a GeoJSON geometry."""
    if "coordinates" not in geom:
        raise ValueError("GeoJSON geometry missing 'coordinates'")
    return geom["coordinates"]


def _geom_type_polygonal(geom: Dict[str, Any]) -> str:
    """Accept only Polygon/MultiPolygon; raise otherwise."""
    t = geom.get("type")
    if t not in ("Polygon", "MultiPolygon"):
        raise ValueError(f"Only Polygon/MultiPolygon supported, got: {t}")
    return t


def _bbox_of_polygon_coords(rings: List[List[Tuple[float, float]]]) -> Tuple[float, float, float, float]:
    """Compute lon/lat bbox from a polygon's rings (outer + holes)."""
    xs, ys = [], []
    for ring in rings:
        for x, y in ring:
            xs.append(x); ys.append(y)
    return (min(xs), min(ys), max(xs), max(ys))


def _normalize_polygon_coords(coords: List) -> List[List[Tuple[float, float]]]:
    """
    Normalize a Polygon coordinates array into:
    [ [ (lon,lat), ... closed ], [hole...], ... ]
    and ensure rings are closed.
    """
    norm = []
    for ring in coords:
        if len(ring) < 4:
            raise ValueError("Polygon ring must have >= 4 coordinates (closed)")
        if ring[0] != ring[-1]:
            ring = list(ring) + [tuple(ring[0])]
        norm.append([tuple(p) for p in ring])
    return norm


def _normalize_multipolygon_coords(coords: List) -> List[List[List[Tuple[float, float]]]]:
    """Normalize a MultiPolygon into list-of-polygons-of-rings."""
    return [_normalize_polygon_coords(poly) for poly in coords]


def _shoelace_area_perimeter_lonlat(ring: List[Tuple[float, float]], lat_scale: float) -> Tuple[float, float]:
    """
    Fallback area/perimeter on a lon/lat plane, using a local metric conversion:

    x = R * cos(lat0) * dlon(rad)
    y = R * dlat(rad)

    This is a robust approximation for city/county-scale AOIs when pyproj is not available.
    """
    R = 6371008.8  # Mean Earth radius (m)
    def to_m_xy(lon: float, lat: float) -> Tuple[float, float]:
        x = math.radians(lon) * R * lat_scale
        y = math.radians(lat) * R
        return x, y

    area2 = 0.0
    perim = 0.0
    n = len(ring)
    for i in range(n):
        x1, y1 = to_m_xy(ring[i][0], ring[i][1])
        x2, y2 = to_m_xy(ring[(i + 1) % n][0], ring[(i + 1) % n][1])
        area2 += (x1 * y2 - x2 * y1)
        perim += math.hypot(x2 - x1, y2 - y1)
    area = abs(area2) * 0.5
    return area, perim


def _geod_area_perimeter_polygon(coords: List[List[Tuple[float, float]]]) -> Tuple[float, float]:
    """
    Compute polygon area/perimeter from rings (first is outer, others are holes).
    - If pyproj.Geod is available, use it (accurate ellipsoidal).
    - Otherwise, use the local-planar approximation described above.
    """
    if _GEOD is None:
        outer = coords[0]
        lat0 = sum(p[1] for p in outer) / max(1, len(outer))
        lat_scale = math.cos(math.radians(lat0))
        a0, p0 = _shoelace_area_perimeter_lonlat(outer, lat_scale)
        area = a0
        perim = p0
        for hole in coords[1:]:
            ah, ph = _shoelace_area_perimeter_lonlat(hole, lat_scale)
            area -= ah
            perim += ph
        return area, perim

    area_total = 0.0
    perim_total = 0.0
    for ring in coords:
        lons, lats = zip(*ring)
        area, perim = _GEOD.polygon_area_perimeter(lons, lats)
        area_total += area
        perim_total += perim
    return abs(area_total), perim_total


def _polygon_centroid(ring: List[Tuple[float, float]]) -> Tuple[float, float]:
    """
    Shoelace centroid on lon/lat (outer ring only).
    For degenerate polygons, fallback to mean of vertices.
    """
    xsum = 0.0
    ysum = 0.0
    area2 = 0.0
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        cross = x1 * y2 - x2 * y1
        xsum += (x1 + x2) * cross
        ysum += (y1 + y2) * cross
        area2 += cross
    if abs(area2) < 1e-12:
        xs = [p[0] for p in ring]; ys = [p[1] for p in ring]
        return (sum(xs) / len(xs), sum(ys) / len(ys))
    cx = xsum / (3.0 * area2)
    cy = ysum / (3.0 * area2)
    return (cx, cy)


def _haversine_distance_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Haversine great-circle distance (meters) on a spherical Earth."""
    R = 6371008.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlmb/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


# -------------------------
# Point-in-polygon helpers
# -------------------------
def _point_in_ring(lon: float, lat: float, ring: List[Tuple[float, float]]) -> bool:
    """
    Ray casting algorithm (ring is expected to be closed).
    For edges exactly on the ray line, this follows a typical toggle approach.
    """
    inside = False
    n = len(ring)
    for i in range(n - 1):
        x1, y1 = ring[i]
        x2, y2 = ring[i + 1]
        if ((y1 > lat) != (y2 > lat)):
            xinters = (x2 - x1) * (lat - y1) / (y2 - y1 + 1e-15) + x1
            if xinters > lon:
                inside = not inside
    return inside


def _point_in_polygon_with_holes(lon: float, lat: float, poly: List[List[Tuple[float, float]]]) -> bool:
    """Return True if point is in polygon outer ring and not in any holes."""
    if not _point_in_ring(lon, lat, poly[0]):
        return False
    for hole in poly[1:]:
        if _point_in_ring(lon, lat, hole):
            return False
    return True


def _aoi_contains(lon: float, lat: float, gtype: str, gcoords: Union[List, List[List]]) -> bool:
    """Centroid-in-AOI membership check for Polygon/MultiPolygon (zero-deps)."""
    if gtype == "Polygon":
        poly = _normalize_polygon_coords(gcoords)
        return _point_in_polygon_with_holes(lon, lat, poly)
    else:
        mpoly = _normalize_multipolygon_coords(gcoords)
        for poly in mpoly:
            if _point_in_polygon_with_holes(lon, lat, poly):
                return True
        return False


# -------------------------------------------------------------------
# Tool handlers
# -------------------------------------------------------------------
def aoi_validate_handler(arguments: dict, context: dict, account=None) -> Dict[str, Any]:
    """
    Validate & normalize an AOI GeoJSON (Polygon/MultiPolygon).
    Return FeatureCollection with per-polygon centroid/area/perimeter and AOI-level bbox.
    """
    geojson_like = arguments.get("geojson")
    if not geojson_like:
        raise ValueError("Missing required parameter: 'geojson'")

    gj = _ensure_geojson_obj(geojson_like)

    # Accept Feature / FeatureCollection / Geometry
    if gj.get("type") == "Feature":
        geom = gj.get("geometry", {})
    elif gj.get("type") == "FeatureCollection":
        feats = gj.get("features", [])
        if not feats:
            raise ValueError("Empty FeatureCollection")
        geom = feats[0].get("geometry", {})
    else:
        geom = gj

    gtype = _geom_type_polygonal(geom)
    coords = _extract_coords(geom)

    result_features = []
    bbox_all = [math.inf, math.inf, -math.inf, -math.inf]
    area_sum = 0.0
    perim_sum = 0.0
    approx_used = (_GEOD is None)

    if gtype == "Polygon":
        poly = _normalize_polygon_coords(coords)
        bb = _bbox_of_polygon_coords(poly)
        bbox_all = [min(bbox_all[0], bb[0]), min(bbox_all[1], bb[1]),
                    max(bbox_all[2], bb[2]), max(bbox_all[3], bb[3])]
        a_m2, p_m = _geod_area_perimeter_polygon(poly)
        area_sum += a_m2; perim_sum += p_m
        cx, cy = _polygon_centroid(poly[0])
        result_features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": poly},
            "properties": {
                "centroid": {"lon": cx, "lat": cy},
                "area_m2": a_m2,
                "perimeter_m": p_m
            }
        })
    else:
        mpoly = _normalize_multipolygon_coords(coords)
        for poly in mpoly:
            bb = _bbox_of_polygon_coords(poly)
            bbox_all = [min(bbox_all[0], bb[0]), min(bbox_all[1], bb[1]),
                        max(bbox_all[2], bb[2]), max(bbox_all[3], bb[3])]
            a_m2, p_m = _geod_area_perimeter_polygon(poly)
            area_sum += a_m2; perim_sum += p_m
            cx, cy = _polygon_centroid(poly[0])
            result_features.append({
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": poly},
                "properties": {
                    "centroid": {"lon": cx, "lat": cy},
                    "area_m2": a_m2,
                    "perimeter_m": p_m
                }
            })

    return {
        "aoi_feature_collection": {"type": "FeatureCollection", "features": result_features},
        "geometry_type": gtype,
        "bbox": {
            "min_lon": bbox_all[0], "min_lat": bbox_all[1],
            "max_lon": bbox_all[2], "max_lat": bbox_all[3]
        },
        "total_area_m2": area_sum,
        "total_area_km2": area_sum / 1e6,
        "total_perimeter_m": perim_sum,
        "approximate": approx_used
    }


def area_handler(arguments: dict, context: dict, account=None) -> Dict[str, Any]:
    """
    Compute AOI area (m², km²). Optionally estimate pixels by GSD.

    Params:
      - geojson: Polygon/MultiPolygon (Feature/FeatureCollection allowed)
      - gsd_m: optional; if provided, returns pixel_estimate = area / gsd^2
      - gsd_x_m, gsd_y_m: optional anisotropic GSD (overrides gsd_m)
    """
    geojson_like = arguments.get("geojson")
    if not geojson_like:
        raise ValueError("Missing required parameter: 'geojson'")

    gsd_m = arguments.get("gsd_m")
    gsd_x_m = arguments.get("gsd_x_m")
    gsd_y_m = arguments.get("gsd_y_m")

    res = aoi_validate_handler({"geojson": geojson_like}, context, account)
    area_m2 = float(res["total_area_m2"])

    px_area = None
    px_est = None
    if gsd_x_m and gsd_y_m:
        px_area = float(gsd_x_m) * float(gsd_y_m)
    elif gsd_m:
        px_area = float(gsd_m) ** 2

    if px_area and px_area > 0:
        px_est = area_m2 / px_area

    return {
        "area_m2": area_m2,
        "area_km2": area_m2 / 1e6,
        "pixel_area_m2": px_area,
        "pixel_estimate": px_est,
        "meta": {"used_geodetic": not res["approximate"]}
    }


def distance_handler(arguments: dict, context: dict, account=None) -> Dict[str, Any]:
    """
    Geodesic distance between two lon/lat points.

    Params:
      - lon1, lat1, lon2, lat2: floats
    """
    try:
        lon1 = float(arguments.get("lon1"))
        lat1 = float(arguments.get("lat1"))
        lon2 = float(arguments.get("lon2"))
        lat2 = float(arguments.get("lat2"))
    except Exception:
        raise ValueError("Invalid coordinates; require numeric lon1, lat1, lon2, lat2")

    if _GEOD is not None:
        _, _, dist_m = _GEOD.inv(lon1, lat1, lon2, lat2)
    else:
        dist_m = _haversine_distance_m(lon1, lat1, lon2, lat2)

    return {"distance_m": dist_m, "distance_km": dist_m / 1000.0}


def pixel_area_handler(arguments: dict, context: dict, account=None) -> Dict[str, Any]:
    """
    Pixel count -> area.

    Params:
      - pixels: number of pixels (float/int)
      - gsd_m: for square pixels
      - gsd_x_m, gsd_y_m: for anisotropic pixels (overrides gsd_m)
    """
    try:
        pixels = float(arguments.get("pixels"))
    except Exception:
        raise ValueError("Missing or invalid 'pixels'")

    gsd_x_m = arguments.get("gsd_x_m")
    gsd_y_m = arguments.get("gsd_y_m")
    gsd_m = arguments.get("gsd_m")

    if gsd_x_m and gsd_y_m:
        px_area = float(gsd_x_m) * float(gsd_y_m)
    elif gsd_m:
        px_area = float(gsd_m) ** 2
    else:
        raise ValueError("Provide either 'gsd_m' or both 'gsd_x_m' and 'gsd_y_m'")

    area_m2 = pixels * px_area
    return {"area_m2": area_m2, "area_km2": area_m2 / 1e6, "pixel_area_m2": px_area}


def pixels_from_area_handler(arguments: dict, context: dict, account=None) -> Dict[str, Any]:
    """
    Area -> pixel count estimate.

    Params:
      - area_m2: area in square meters
      - gsd_m or (gsd_x_m, gsd_y_m)
      - rounding: "floor"|"ceil"|"round" (default "round")
    """
    try:
        area_m2 = float(arguments.get("area_m2"))
    except Exception:
        raise ValueError("Missing or invalid 'area_m2'")

    rounding = (arguments.get("rounding") or "round").lower()
    gsd_x_m = arguments.get("gsd_x_m")
    gsd_y_m = arguments.get("gsd_y_m")
    gsd_m = arguments.get("gsd_m")

    if gsd_x_m and gsd_y_m:
        px_area = float(gsd_x_m) * float(gsd_y_m)
    elif gsd_m:
        px_area = float(gsd_m) ** 2
    else:
        raise ValueError("Provide either 'gsd_m' or both 'gsd_x_m' and 'gsd_y_m'")

    if px_area <= 0:
        raise ValueError("Pixel area must be > 0")

    px_float = area_m2 / px_area
    if rounding == "floor":
        px_int = math.floor(px_float)
    elif rounding == "ceil":
        px_int = math.ceil(px_float)
    else:
        px_int = int(round(px_float))

    return {"pixels_est_float": px_float, "pixels_int": px_int, "pixel_area_m2": px_area}


def gridify_handler(arguments: dict, context: dict, account=None) -> Dict[str, Any]:
    """
    Create a regular grid over the AOI.

    Modes:
      - mode="size": specify cell_width_m/cell_height_m in meters (default 100m square)
      - mode="shape": specify rows/cols to equally divide the AOI bbox

    Optional:
      - clip: bool, keep only cells whose centroid lies inside AOI (zero-deps clipping)

    Notes:
      - The conversion meters<->degrees is local at the outer-ring centroid latitude.
      - For large AOIs or cross-latitudinal spans, consider upgrading to projected math.
    """
    geojson_like = arguments.get("geojson")
    if not geojson_like:
        raise ValueError("Missing required parameter: 'geojson'")

    mode = (arguments.get("mode") or "size").lower()
    clip = bool(arguments.get("clip", False))

    cell_width_m = float(arguments.get("cell_width_m", 100.0))
    cell_height_m = float(arguments.get("cell_height_m", cell_width_m))
    rows = arguments.get("rows")
    cols = arguments.get("cols")

    gj = _ensure_geojson_obj(geojson_like)
    if gj.get("type") == "Feature":
        geom = gj.get("geometry", {})
    elif gj.get("type") == "FeatureCollection":
        feats = gj.get("features", [])
        if not feats:
            raise ValueError("Empty FeatureCollection")
        geom = feats[0].get("geometry", {})
    else:
        geom = gj

    gtype = _geom_type_polygonal(geom)
    coords = _extract_coords(geom)

    # AOI bbox and reference latitude
    if gtype == "Polygon":
        poly = _normalize_polygon_coords(coords)
        bbox = _bbox_of_polygon_coords(poly)
        ref_lon, ref_lat = _polygon_centroid(poly[0])
    else:
        mpoly = _normalize_multipolygon_coords(coords)
        bbox = [math.inf, math.inf, -math.inf, -math.inf]
        ref_lon, ref_lat = _polygon_centroid(mpoly[0][0])
        for poly in mpoly:
            bb = _bbox_of_polygon_coords(poly)
            bbox = [min(bbox[0], bb[0]), min(bbox[1], bb[1]),
                    max(bbox[2], bb[2]), max(bbox[3], bb[3])]

    min_lon, min_lat, max_lon, max_lat = bbox

    # Local meters->degrees conversion
    R = 6371008.8
    deg_per_meter_lat = (180.0 / math.pi) / R
    deg_per_meter_lon = (180.0 / math.pi) / (R * max(1e-9, math.cos(math.radians(ref_lat))))

    # Determine grid spacing (dlon/dlat) and rows/cols
    if mode == "shape":
        try:
            rows = int(rows); cols = int(cols)
            if rows <= 0 or cols <= 0:
                raise ValueError
        except Exception:
            raise ValueError("mode='shape' requires positive integer 'rows' and 'cols'")
        dlon = (max_lon - min_lon) / cols
        dlat = (max_lat - min_lat) / rows
    else:
        if cell_width_m <= 0 or cell_height_m <= 0:
            raise ValueError("cell_width_m and cell_height_m must be > 0")
        dlon = cell_width_m * deg_per_meter_lon
        dlat = cell_height_m * deg_per_meter_lat
        cols = max(1, int(math.ceil((max_lon - min_lon) / dlon)))
        rows = max(1, int(math.ceil((max_lat - min_lat) / dlat)))

    # Generate grid cells
    features = []
    id_counter = 0
    for r in range(rows):
        lat0 = min_lat + r * dlat
        lat1 = min(lat0 + dlat, max_lat)
        for c in range(cols):
            lon0 = min_lon + c * dlon
            lon1 = min(lon0 + dlon, max_lon)

            clon = 0.5 * (lon0 + lon1)
            clat = 0.5 * (lat0 + lat1)
            if clip and (not _aoi_contains(clon, clat, gtype, coords)):
                continue

            polygon = [
                [lon0, lat0],
                [lon1, lat0],
                [lon1, lat1],
                [lon0, lat1],
                [lon0, lat0]
            ]
            features.append({
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [polygon]},
                "properties": {
                    "id": id_counter,
                    "row": r, "col": c,
                    "centroid": {"lon": clon, "lat": clat},
                    "bounds": {"min_lon": lon0, "min_lat": lat0, "max_lon": lon1, "max_lat": lat1}
                }
            })
            id_counter += 1

    return {"type": "FeatureCollection", "features": features,
            "meta": {"mode": mode, "rows": rows, "cols": cols, "reference_lat": ref_lat}}


def _normalize_lines(geom: Dict[str, Any]) -> List[List[Tuple[float, float]]]:
    """Normalize LineString/MultiLineString into list of lines (list of (lon,lat))."""
    gtype = geom.get("type")
    if gtype == "LineString":
        coords = geom.get("coordinates", [])
        if len(coords) < 2:
            raise ValueError("LineString must have >= 2 points")
        return [[tuple(p) for p in coords]]
    elif gtype == "MultiLineString":
        lines = []
        for line in geom.get("coordinates", []):
            if len(line) < 2:
                continue
            lines.append([tuple(p) for p in line])
        if not lines:
            raise ValueError("Empty MultiLineString")
        return lines
    else:
        raise ValueError(f"Only LineString/MultiLineString supported, got: {gtype}")


def line_length_handler(arguments: dict, context: dict, account=None) -> Dict[str, Any]:
    """
    Compute geodesic length of a LineString/MultiLineString.

    Params:
      - geojson: Geometry/Feature/FeatureCollection (first line geometry will be used)
    """
    geojson_like = arguments.get("geojson")
    if not geojson_like:
        raise ValueError("Missing required parameter: 'geojson'")

    gj = _ensure_geojson_obj(geojson_like)
    # Find the first line geometry
    if gj.get("type") == "Feature":
        geom = gj.get("geometry", {})
    elif gj.get("type") == "FeatureCollection":
        feats = gj.get("features", [])
        if not feats:
            raise ValueError("Empty FeatureCollection")
        geom = None
        for f in feats:
            gt = f.get("geometry", {}).get("type")
            if gt in ("LineString", "MultiLineString"):
                geom = f.get("geometry", {})
                break
        if geom is None:
            raise ValueError("No LineString/MultiLineString feature found")
    else:
        geom = gj

    lines = _normalize_lines(geom)

    total_m = 0.0
    if _GEOD is not None:
        for line in lines:
            for i in range(len(line) - 1):
                lon1, lat1 = line[i]
                lon2, lat2 = line[i + 1]
                _, _, d = _GEOD.inv(lon1, lat1, lon2, lat2)
                total_m += d
    else:
        for line in lines:
            for i in range(len(line) - 1):
                lon1, lat1 = line[i]
                lon2, lat2 = line[i + 1]
                total_m += _haversine_distance_m(lon1, lat1, lon2, lat2)

    return {"length_m": total_m, "length_km": total_m / 1000.0}


# -------------------------------------------------------------------
# Toolkit registration (same style as your example)
# -------------------------------------------------------------------
def setup(registrar):
    """Entry point called by the platform to register this toolkit and tools."""
    registrar.toolkit(
        name="geo_basic",
        description="Geo basics: AOI validate/area, geodesic distance, pixel-area conversions, gridify, line length",
        version="0.3.0"
    )

    # 1) AOI validate
    registrar.tool(
        ToolSpec(
            slug="geo_basic.aoi_validate",
            name="AOI Validate",
            description="Validate & normalize Polygon/MultiPolygon GeoJSON; return bbox, centroid, area, perimeter.",
            parameters={
                "type": "object",
                "properties": {
                    "geojson": {
                        "oneOf": [
                            {"type": "string", "description": "GeoJSON string (Feature/FeatureCollection/Geometry)"},
                            {"type": "object", "description": "GeoJSON object (Feature/FeatureCollection/Geometry)"}
                        ]
                    }
                },
                "required": ["geojson"]
            },
            requires_connection=False
        ),
        aoi_validate_handler
    )

    # 2) AOI area (+ optional pixel estimate)
    registrar.tool(
        ToolSpec(
            slug="geo_basic.area",
            name="AOI Area",
            description="Compute AOI area (m², km²), optionally estimate pixels by GSD.",
            parameters={
                "type": "object",
                "properties": {
                    "geojson": {
                        "oneOf": [{"type": "string"}, {"type": "object"}],
                        "description": "Polygon/MultiPolygon or Feature/FeatureCollection"
                    },
                    "gsd_m": {"type": "number", "description": "Square pixel size (m), e.g., 10 for Sentinel-2"},
                    "gsd_x_m": {"type": "number", "description": "Pixel size in X (m). If set with gsd_y_m, overrides gsd_m"},
                    "gsd_y_m": {"type": "number", "description": "Pixel size in Y (m). If set with gsd_x_m, overrides gsd_m"}
                },
                "required": ["geojson"]
            },
            requires_connection=False
        ),
        area_handler
    )

    # 3) Distance
    registrar.tool(
        ToolSpec(
            slug="geo_basic.distance",
            name="Distance",
            description="Geodesic distance between two lon/lat points (WGS84).",
            parameters={
                "type": "object",
                "properties": {
                    "lon1": {"type": "number"},
                    "lat1": {"type": "number"},
                    "lon2": {"type": "number"},
                    "lat2": {"type": "number"}
                },
                "required": ["lon1", "lat1", "lon2", "lat2"]
            },
            requires_connection=False
        ),
        distance_handler
    )

    # 4) Pixel -> Area
    registrar.tool(
        ToolSpec(
            slug="geo_basic.pixel_area",
            name="Pixel → Area",
            description="Compute area from pixel count and GSD (supports anisotropic pixels).",
            parameters={
                "type": "object",
                "properties": {
                    "pixels": {"type": "number", "description": "Number of pixels (e.g., valid mask pixels)"},
                    "gsd_m": {"type": "number", "description": "Square pixel size (m)"},
                    "gsd_x_m": {"type": "number", "description": "Pixel size X (m)"},
                    "gsd_y_m": {"type": "number", "description": "Pixel size Y (m)"}
                },
                "required": ["pixels"]
            },
            requires_connection=False
        ),
        pixel_area_handler
    )

    # 5) Area -> Pixels
    registrar.tool(
        ToolSpec(
            slug="geo_basic.pixels_from_area",
            name="Area → Pixels",
            description="Estimate pixel count from area and GSD (supports anisotropic pixels).",
            parameters={
                "type": "object",
                "properties": {
                    "area_m2": {"type": "number", "description": "Area in square meters"},
                    "gsd_m": {"type": "number", "description": "Square pixel size (m)"},
                    "gsd_x_m": {"type": "number", "description": "Pixel size X (m)"},
                    "gsd_y_m": {"type": "number", "description": "Pixel size Y (m)"},
                    "rounding": {"type": "string", "enum": ["floor", "ceil", "round"], "default": "round"}
                },
                "required": ["area_m2"]
            },
            requires_connection=False
        ),
        pixels_from_area_handler
    )

    # 6) Gridify
    registrar.tool(
        ToolSpec(
            slug="geo_basic.gridify",
            name="AOI Gridify",
            description="Create a regular grid over the AOI (by cell size in meters or by rows/cols). Optional centroid-in-AOI clipping.",
            parameters={
                "type": "object",
                "properties": {
                    "geojson": {
                        "oneOf": [{"type": "string"}, {"type": "object"}],
                        "description": "AOI Polygon/MultiPolygon or Feature/FeatureCollection"
                    },
                    "mode": {"type": "string", "enum": ["size", "shape"], "default": "size"},
                    "cell_width_m": {"type": "number", "description": "Cell width in meters (mode='size')", "default": 100},
                    "cell_height_m": {"type": "number", "description": "Cell height in meters (mode='size')"},
                    "rows": {"type": "integer", "description": "Number of rows (mode='shape')"},
                    "cols": {"type": "integer", "description": "Number of cols (mode='shape')"},
                    "clip": {"type": "boolean", "description": "Keep cells whose centroid lies inside AOI", "default": False}
                },
                "required": ["geojson"]
            },
            requires_connection=False
        ),
        gridify_handler
    )

    # 7) Line length
    registrar.tool(
        ToolSpec(
            slug="geo_basic.line_length",
            name="Line Length",
            description="Compute geodesic length of a LineString/MultiLineString.",
            parameters={
                "type": "object",
                "properties": {
                    "geojson": {
                        "oneOf": [{"type": "string"}, {"type": "object"}],
                        "description": "LineString/MultiLineString or Feature/FeatureCollection containing such geometry"
                    }
                },
                "required": ["geojson"]
            },
            requires_connection=False
        ),
        line_length_handler
    )
