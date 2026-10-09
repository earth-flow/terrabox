"""Scientific preflight and water-label evidence for aligned rasters and single scenes."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from ..core.registry import ToolSpec


_REASON_ORDER = (
    "grid_mismatch",
    "shape_mismatch",
    "crs_mismatch",
    "transform_mismatch",
    "bounds_mismatch",
    "resolution_mismatch",
    "nodata_mismatch",
    "valid_mask_mismatch",
)


def _rasterio_numpy():
    try:
        import numpy as np
        import rasterio
    except ImportError as exc:
        raise ImportError("geo_water requires the Terrabox geo dependencies: pip install -e '.[geo]'") from exc
    return rasterio, np


def _profile(src) -> dict[str, Any]:
    return {
        "width": src.width,
        "height": src.height,
        "shape": [src.height, src.width],
        "count": src.count,
        "crs": src.crs.to_string() if src.crs else None,
        "transform": list(src.transform)[:6],
        "bounds": [src.bounds.left, src.bounds.bottom, src.bounds.right, src.bounds.top],
        "resolution": list(src.res),
        "nodata": list(src.nodatavals),
        "dtype": list(src.dtypes),
    }


def _grid_id(profile: dict[str, Any]) -> str:
    canonical = {
        "shape": profile["shape"],
        "crs": profile["crs"],
        "transform": profile["transform"],
    }
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return f"grid:{digest[:16]}"


# Projections whose scale grows with latitude (area factor sec^2 of latitude):
# pixel counts times the nominal pixel area misstate ground area, often by tens
# of percent. Transverse Mercator (UTM) is not in this family.
_AREA_DISTORTING_METHODS = (
    "popular visualisation pseudo mercator",
    "mercator (variant a)",
    "mercator (variant b)",
    "mercator (variant c)",
    "mercator (spherical)",
    "mercator",
)


def _area_support(crs, transform) -> dict[str, Any]:
    """Nominal per-pixel ground area, or the reason it cannot be used.

    Requires a projected CRS with linear axis units and a projection that does
    not scale area with latitude. Geographic (degree) grids are refused rather
    than squaring an angular pixel size.
    """
    if crs is None or not crs.is_projected:
        return {"reason_code": "unsupported_area_crs", "crs": crs.to_string() if crs else None}
    try:
        from pyproj import CRS
    except ImportError as exc:
        raise ImportError("geo_water area calculation requires pyproj from the Terrabox geo dependencies") from exc
    projected = CRS.from_user_input(crs)
    operation = projected.coordinate_operation
    method = operation.method_name if operation is not None else None
    if method and method.strip().lower() in _AREA_DISTORTING_METHODS:
        return {"reason_code": "area_distorting_projection", "crs": crs.to_string(), "projection_method": method}
    axes = projected.axis_info
    if len(axes) < 2 or not all(axis.unit_conversion_factor for axis in axes[:2]):
        return {"reason_code": "unsupported_area_units", "crs": crs.to_string(), "projection_method": method}
    pixel_area_m2 = abs(transform.a * transform.e - transform.b * transform.d)
    pixel_area_m2 *= axes[0].unit_conversion_factor * axes[1].unit_conversion_factor
    if not math.isfinite(pixel_area_m2) or pixel_area_m2 <= 0:
        return {"reason_code": "invalid_pixel_area", "crs": crs.to_string(), "projection_method": method}
    return {"reason_code": None, "crs": crs.to_string(), "projection_method": method, "pixel_area_m2": pixel_area_m2}


def _pair_preflight(before_path: str, after_path: str, before_grid_id: str | None = None,
                    after_grid_id: str | None = None) -> dict[str, Any]:
    rasterio, np = _rasterio_numpy()
    with rasterio.open(before_path) as before, rasterio.open(after_path) as after:
        before_profile = _profile(before)
        after_profile = _profile(after)
        differences = []

        declared_ids = (before_grid_id, after_grid_id)
        if any(value is not None for value in declared_ids):
            if not all(isinstance(value, str) and value.strip() for value in declared_ids):
                differences.append("grid_mismatch")
            elif before_grid_id != after_grid_id:
                differences.append("grid_mismatch")

        comparisons = (
            ("shape", "shape_mismatch"),
            ("crs", "crs_mismatch"),
            ("transform", "transform_mismatch"),
            ("bounds", "bounds_mismatch"),
            ("resolution", "resolution_mismatch"),
            ("nodata", "nodata_mismatch"),
        )
        for field, reason in comparisons:
            if before_profile[field] != after_profile[field]:
                differences.append(reason)

        if before.count < 1 or after.count < 1:
            differences.append("profile_mismatch")
        elif before.width == after.width and before.height == after.height:
            before_valid = before.dataset_mask() > 0
            after_valid = after.dataset_mask() > 0
            if not np.array_equal(before_valid, after_valid):
                differences.append("valid_mask_mismatch")
            common_valid_pixels = int(np.count_nonzero(before_valid & after_valid))
        else:
            common_valid_pixels = None

    reason_code = next((reason for reason in _REASON_ORDER if reason in differences), None)
    if reason_code is None and differences:
        reason_code = differences[0]
    matched_grid_id = _grid_id(before_profile) if not differences else None
    return {
        "success": not differences,
        "execution_blocked": bool(differences),
        "reason_code": reason_code,
        "failed_checks": differences,
        "grid_id": matched_grid_id,
        "declared_grid_ids": {"before": before_grid_id, "after": after_grid_id},
        "common_valid_pixels": common_valid_pixels,
        "before": before_profile,
        "after": after_profile,
    }


def raster_profile_preflight_handler(arguments: dict, context: Any, account: Any) -> dict[str, Any]:
    """Compare complete raster grids and masks before pixel-wise analysis."""
    return _pair_preflight(
        arguments["before_path"],
        arguments["after_path"],
        arguments.get("before_grid_id"),
        arguments.get("after_grid_id"),
    )


def water_evidence_handler(arguments: dict, context: Any, account: Any) -> dict[str, Any]:
    """Summarize supplied 0/1 semantic water labels over common valid support."""
    rasterio, np = _rasterio_numpy()
    before_path = arguments["before_path"]
    after_path = arguments["after_path"]
    check = _pair_preflight(
        before_path,
        after_path,
        arguments.get("before_grid_id"),
        arguments.get("after_grid_id"),
    )
    if check["execution_blocked"]:
        return {**check, "semantic_class": "water_not_flood", "change_answerable": False}

    with rasterio.open(before_path) as before, rasterio.open(after_path) as after:
        before_data = before.read(1)
        after_data = after.read(1)
        valid = (before.dataset_mask() > 0) & (after.dataset_mask() > 0)
        before_valid = np.isfinite(before_data) & np.isin(before_data, (0, 1))
        after_valid = np.isfinite(after_data) & np.isin(after_data, (0, 1))
        valid &= before_valid & after_valid

        invalid_labels = int(np.count_nonzero(
            ((before.dataset_mask() > 0) & ~before_valid) | ((after.dataset_mask() > 0) & ~after_valid)
        ))
        if invalid_labels:
            return {
                "success": False,
                "execution_blocked": True,
                "reason_code": "invalid_water_labels",
                "failed_checks": ["invalid_water_labels"],
                "invalid_label_pixels": invalid_labels,
                "semantic_class": "water_not_flood",
                "change_answerable": False,
            }

        area = _area_support(before.crs, before.transform)
        if area.get("reason_code"):
            return {
                "success": False,
                "execution_blocked": True,
                "reason_code": area["reason_code"],
                "failed_checks": [area["reason_code"]],
                "semantic_class": "water_not_flood",
                "change_answerable": False,
                "crs": area.get("crs"),
                "projection_method": area.get("projection_method"),
            }
        pixel_area_m2 = area["pixel_area_m2"]

        valid_pixels = int(np.count_nonzero(valid))
        total_pixels = int(valid.size)
        before_water = int(np.count_nonzero(valid & (before_data == 1)))
        after_water = int(np.count_nonzero(valid & (after_data == 1)))
        new_water = int(np.count_nonzero(valid & (before_data == 0) & (after_data == 1)))
        receded_water = int(np.count_nonzero(valid & (before_data == 1) & (after_data == 0)))
        common_valid_area = valid_pixels * pixel_area_m2
        before_profile = _profile(before)
        after_profile = _profile(after)

    return {
        "success": valid_pixels > 0,
        "execution_blocked": valid_pixels == 0,
        "reason_code": None if valid_pixels else "no_common_valid_pixels",
        "failed_checks": [] if valid_pixels else ["no_common_valid_pixels"],
        "semantic_class": "water_not_flood",
        "support": "common_valid_pair",
        "grid_id": check["grid_id"],
        "source_ids": {"before": str(Path(before_path)), "after": str(Path(after_path))},
        "crs": before_profile["crs"],
        "transform": before_profile["transform"],
        "area_method": "affine_pixel_area_with_projected_crs_unit_conversion",
        "projection_method": area["projection_method"],
        "pixel_area_m2": pixel_area_m2,
        "valid_pixels": valid_pixels,
        "excluded_pixels": total_pixels - valid_pixels,
        "valid_area_m2": common_valid_area if valid_pixels else None,
        "before_water_pixels": before_water if valid_pixels else None,
        "after_water_pixels": after_water if valid_pixels else None,
        "before_water_area_m2": before_water * pixel_area_m2 if valid_pixels else None,
        "after_water_area_m2": after_water * pixel_area_m2 if valid_pixels else None,
        "new_water_area_m2": new_water * pixel_area_m2 if valid_pixels else None,
        "receded_water_area_m2": receded_water * pixel_area_m2 if valid_pixels else None,
        "net_water_change_m2": (after_water - before_water) * pixel_area_m2 if valid_pixels else None,
        "change_answerable": valid_pixels > 0,
        "limitations": [
            "Statistics describe supplied 0/1 water labels, not flood causation or segmentation accuracy.",
            "New-water labels do not establish inundation without validated observations and task-specific evidence.",
        ],
    }


def water_extent_handler(arguments: dict, context: Any, account: Any) -> dict[str, Any]:
    """Water area of one 0/1 semantic water-label raster over its valid pixels."""
    rasterio, np = _rasterio_numpy()
    label_path = arguments["label_path"]
    with rasterio.open(label_path) as src:
        data = src.read(1)
        dataset_valid = src.dataset_mask() > 0
        label_valid = np.isfinite(data) & np.isin(data, (0, 1))
        invalid_labels = int(np.count_nonzero(dataset_valid & ~label_valid))
        profile = _profile(src)
        area = _area_support(src.crs, src.transform)
    blocked = {"semantic_class": "water_not_flood", "extent_answerable": False, "crs": profile["crs"]}
    if profile["count"] != 1:
        return {**blocked, "success": False, "execution_blocked": True,
                "reason_code": "unsupported_band_count", "failed_checks": ["unsupported_band_count"]}
    if invalid_labels:
        return {**blocked, "success": False, "execution_blocked": True, "reason_code": "invalid_water_labels",
                "failed_checks": ["invalid_water_labels"], "invalid_label_pixels": invalid_labels}
    if area.get("reason_code"):
        return {**blocked, "success": False, "execution_blocked": True, "reason_code": area["reason_code"],
                "failed_checks": [area["reason_code"]], "projection_method": area.get("projection_method")}
    valid = dataset_valid & label_valid
    valid_pixels = int(np.count_nonzero(valid))
    total_pixels = int(valid.size)
    if valid_pixels == 0:
        return {**blocked, "success": False, "execution_blocked": True,
                "reason_code": "no_valid_pixels", "failed_checks": ["no_valid_pixels"]}
    water_pixels = int(np.count_nonzero(valid & (data == 1)))
    pixel_area_m2 = area["pixel_area_m2"]
    return {
        "success": True,
        "execution_blocked": False,
        "reason_code": None,
        "failed_checks": [],
        "semantic_class": "water_not_flood",
        "support": "valid_pixels_of_scene",
        "source_id": str(Path(label_path)),
        "grid_id": _grid_id(profile),
        "crs": profile["crs"],
        "transform": profile["transform"],
        "resolution": profile["resolution"],
        "area_method": "affine_pixel_area_with_projected_crs_unit_conversion",
        "projection_method": area["projection_method"],
        "pixel_area_m2": pixel_area_m2,
        "valid_pixels": valid_pixels,
        "excluded_pixels": total_pixels - valid_pixels,
        "valid_area_m2": valid_pixels * pixel_area_m2,
        "water_pixels": water_pixels,
        "water_area_m2": water_pixels * pixel_area_m2,
        "water_fraction": water_pixels / valid_pixels,
        "extent_answerable": True,
        "limitations": [
            "Statistics describe supplied 0/1 water labels, not flood extent or segmentation accuracy.",
            "One scene shows water at one time; it does not show change or inundation.",
        ],
    }


def setup(registrar) -> None:
    registrar.toolkit(
        name="geo_water",
        description="Scientific grid preflight and area statistics for semantic water-label rasters (paired or single scene).",
        version="0.1.0",
    )
    registrar.tool(
        ToolSpec(
            slug="geo_water.raster_profile_preflight",
            name="Raster Profile Preflight",
            description="Compare grid ID, shape, CRS, transform, bounds, resolution, nodata and valid masks before paired raster analysis.",
            parameters={
                "type": "object",
                "properties": {
                    "before_path": {"type": "string"},
                    "after_path": {"type": "string"},
                    "before_grid_id": {"type": "string"},
                    "after_grid_id": {"type": "string"},
                },
                "required": ["before_path", "after_path"],
            },
            requires_connection=False,
        ),
        raster_profile_preflight_handler,
    )
    registrar.tool(
        ToolSpec(
            slug="geo_water.water_evidence",
            name="Water Label Evidence",
            description="Compute paired water-label area only after grid preflight. Inputs must be aligned semantic rasters with values 0=non-water, 1=water and nodata masked.",
            parameters={
                "type": "object",
                "properties": {
                    "before_path": {"type": "string"},
                    "after_path": {"type": "string"},
                    "before_grid_id": {"type": "string"},
                    "after_grid_id": {"type": "string"},
                },
                "required": ["before_path", "after_path"],
            },
            requires_connection=False,
        ),
        water_evidence_handler,
    )
    registrar.tool(
        ToolSpec(
            slug="geo_water.water_extent",
            name="Water Label Extent",
            description="Compute water area of one semantic water-label raster (0=non-water, 1=water, nodata masked) over its valid pixels. Blocks geographic grids and area-distorting projections.",
            parameters={
                "type": "object",
                "properties": {"label_path": {"type": "string"}},
                "required": ["label_path"],
            },
            requires_connection=False,
        ),
        water_extent_handler,
    )
