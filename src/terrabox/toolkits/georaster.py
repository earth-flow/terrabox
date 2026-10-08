"""
Geo Raster Toolkit
------------------
A production-ready toolkit for raster-based spectral index calculations and analysis.

Key features:
1. Universal Normalized Difference Calculator (NDVI, NDWI, NDBI, NBR, NDTI, NDSI).
2. Specialized Indices (EVI, WRI, FVC).
3. Advanced Analysis (TVDI, FRP, Snow Loss Statistics).
4. Zero-dependency initialization (lazy imports).
"""

import os
from typing import Any, Dict
from ..core.registry import ToolSpec


# ------------------------------------------------------------------------------
# Lazy Imports & Helpers
# ------------------------------------------------------------------------------

def _lazy_imports():
    try:
        import rasterio
        import numpy as np
        return rasterio, np
    except ImportError:
        raise ImportError("Missing dependencies for geo_raster. Please install: pip install rasterio numpy")


def _lazy_scipy_imports():
    try:
        from scipy.stats import linregress
        from scipy.ndimage import zoom
        return linregress, zoom
    except ImportError:
        raise ImportError("Missing dependencies for advanced analysis. Please install: pip install scipy")


def _save_raster(output_path: str, data: Any, profile: Dict[str, Any], dtype=None, nodata=None):
    """Helper to save raster data to disk."""
    import rasterio

    # Ensure directory exists
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    # Update profile
    new_profile = profile.copy()
    new_profile.update(
        count=1,
        compress='lzw'
    )
    if dtype:
        new_profile['dtype'] = dtype
    if nodata is not None:
        new_profile['nodata'] = nodata

    with rasterio.open(output_path, 'w', **new_profile) as dst:
        dst.write(data, 1)


# ------------------------------------------------------------------------------
# Universal Normalized Difference Calculator
# ------------------------------------------------------------------------------

def calculate_normalized_difference_handler(arguments: Dict[str, Any], context: Any, account: Any) -> Dict[str, Any]:
    """
    Calculate generic Normalized Difference Indices.
    Formula: (Band_A - Band_B) / (Band_A + Band_B)
    """
    rasterio, np = _lazy_imports()
    scipy_zoom = None  # Only needed for NDSI resizing if sizes differ

    band_a_path = arguments.get("band_a_path")
    band_b_path = arguments.get("band_b_path")
    output_path = arguments.get("output_path")
    index_name = arguments.get("index_name", "index").upper()
    scale_factor = float(arguments.get("scale_factor", 1.0))  # E.g. 0.0001 for MODIS

    if not (band_a_path and band_b_path and output_path):
        raise ValueError("Missing required paths: band_a_path, band_b_path, or output_path")

    with rasterio.open(band_a_path) as src_a:
        band_a = src_a.read(1).astype(np.float32)
        profile = src_a.profile

    with rasterio.open(band_b_path) as src_b:
        band_b = src_b.read(1).astype(np.float32)

    # Apply scaling if needed (e.g. for MODIS surface reflectance)
    if scale_factor != 1.0:
        band_a *= scale_factor
        band_b *= scale_factor

    # Handle size mismatch (logic ported from calculate_ndsi in Index.py)
    if band_a.shape != band_b.shape:
        _, zoom = _lazy_scipy_imports()
        target_h = min(band_a.shape[0], band_b.shape[0])
        target_w = min(band_a.shape[1], band_b.shape[1])

        # Helper to resize
        def resize_band(b, target_shape):
            if b.shape == target_shape: return b
            factors = (target_shape[0] / b.shape[0], target_shape[1] / b.shape[1])
            return zoom(b, factors, order=1)

        band_a = resize_band(band_a, (target_h, target_w))
        band_b = resize_band(band_b, (target_h, target_w))
        # Update profile height/width
        profile.update(height=target_h, width=target_w)

    # Filter invalid values
    if scale_factor != 1.0:
        band_a = np.where((band_a < 0) | (band_a > 1), np.nan, band_a)
        band_b = np.where((band_b < 0) | (band_b > 1), np.nan, band_b)

    # Calculation
    denominator = band_a + band_b + 1e-6
    result = (band_a - band_b) / denominator
    result = np.clip(result, -1, 1)

    _save_raster(output_path, result.astype(rasterio.float32), profile, dtype=rasterio.float32, nodata=-9999)

    return {
        "status": "success",
        "message": f"{index_name} calculated.",
        "output_path": output_path
    }


# ------------------------------------------------------------------------------
# Specialized Indices (EVI, FVC, WRI)
# ------------------------------------------------------------------------------

def calculate_evi_handler(arguments: Dict[str, Any], context: Any, account: Any) -> Dict[str, Any]:
    """Calculate Enhanced Vegetation Index (EVI)."""
    rasterio, np = _lazy_imports()

    nir_path = arguments["nir_path"]
    red_path = arguments["red_path"]
    blue_path = arguments["blue_path"]
    output_path = arguments["output_path"]

    G = float(arguments.get("G", 2.5))
    C1 = float(arguments.get("C1", 6.0))
    C2 = float(arguments.get("C2", 7.5))
    L = float(arguments.get("L", 1.0))

    with rasterio.open(nir_path) as src:
        nir = src.read(1).astype(np.float32)
        profile = src.profile
    with rasterio.open(red_path) as src:
        red = src.read(1).astype(np.float32)
    with rasterio.open(blue_path) as src:
        blue = src.read(1).astype(np.float32)

    denominator = nir + C1 * red - C2 * blue + L + 1e-6
    evi = G * (nir - red) / denominator

    _save_raster(output_path, evi.astype(rasterio.float32), profile, dtype=rasterio.float32, nodata=-9999)
    return {"output_path": output_path}


def calculate_fvc_handler(arguments: Dict[str, Any], context: Any, account: Any) -> Dict[str, Any]:
    """Calculate Fractional Vegetation Cover (FVC) from NIR and Red."""
    rasterio, np = _lazy_imports()

    nir_path = arguments["nir_path"]
    red_path = arguments["red_path"]
    output_path = arguments["output_path"]
    ndvi_min = float(arguments.get("ndvi_min", 0.1))
    ndvi_max = float(arguments.get("ndvi_max", 0.9))

    with rasterio.open(nir_path) as src:
        nir = src.read(1).astype(np.float32)
        profile = src.profile
    with rasterio.open(red_path) as src:
        red = src.read(1).astype(np.float32)

    ndvi = (nir - red) / (nir + red + 1e-6)

    # FVC formula
    fvc = ((ndvi - ndvi_min) / (ndvi_max - ndvi_min)) * 100.0
    fvc = np.clip(fvc, 0, 100)

    _save_raster(output_path, fvc.astype(rasterio.float32), profile, dtype=rasterio.float32, nodata=-9999)
    return {"output_path": output_path}


def calculate_wri_handler(arguments: Dict[str, Any], context: Any, account: Any) -> Dict[str, Any]:
    """Calculate Water Ratio Index (WRI): (Green + Red) / (NIR + SWIR)."""
    rasterio, np = _lazy_imports()

    green_path = arguments["green_path"]
    red_path = arguments["red_path"]
    nir_path = arguments["nir_path"]
    swir_path = arguments["swir_path"]
    output_path = arguments["output_path"]

    with rasterio.open(green_path) as src:
        green = src.read(1).astype(np.float32)
        profile = src.profile
    with rasterio.open(red_path) as src:
        red = src.read(1).astype(np.float32)
    with rasterio.open(nir_path) as src:
        nir = src.read(1).astype(np.float32)
    with rasterio.open(swir_path) as src:
        swir = src.read(1).astype(np.float32)

    denominator = nir + swir + 1e-6
    wri = (green + red) / denominator

    _save_raster(output_path, wri.astype(rasterio.float32), profile, dtype=rasterio.float32, nodata=-9999)
    return {"output_path": output_path}


# ------------------------------------------------------------------------------
# Advanced Analysis (TVDI, Snow)
# ------------------------------------------------------------------------------

def compute_tvdi_handler(arguments: Dict[str, Any], context: Any, account: Any) -> Dict[str, Any]:
    """
    Compute Temperature Vegetation Dryness Index (TVDI).
    Uses trapezoidal method with linear regression on LST/NDVI scatter space.
    """
    rasterio, np = _lazy_imports()
    linregress, _ = _lazy_scipy_imports()

    ndvi_path = arguments["ndvi_path"]
    lst_path = arguments["lst_path"]
    output_path = arguments["output_path"]

    with rasterio.open(ndvi_path) as src:
        ndvi = src.read(1).astype(np.float32) * 0.0001
        profile = src.profile
    with rasterio.open(lst_path) as src:
        lst = src.read(1).astype(np.float32) * 0.02

    # Mask valid data
    valid_mask = (ndvi >= 0) & (ndvi <= 1) & (lst > 0)

    if not np.any(valid_mask) or np.sum(valid_mask) < 100:
        tvdi = np.full_like(ndvi, np.nan)
        _save_raster(output_path, tvdi, profile, dtype=rasterio.float32, nodata=-9999)
        return {"output_path": output_path, "warning": "Insufficient valid pixels for TVDI."}

    ndvi_valid = ndvi[valid_mask]
    lst_valid = lst[valid_mask]

    # Binning logic
    n_bins = 100
    bins = np.linspace(ndvi_valid.min(), ndvi_valid.max(), n_bins + 1)
    bin_centers, lst_max_list, lst_min_list = [], [], []

    for i in range(n_bins):
        mask_bin = (ndvi_valid >= bins[i]) & (ndvi_valid < bins[i + 1])
        if np.any(mask_bin):
            bin_centers.append((bins[i] + bins[i + 1]) / 2)
            lst_subset = lst_valid[mask_bin]
            lst_max_list.append(np.max(lst_subset))
            lst_min_list.append(np.min(lst_subset))

    if len(bin_centers) < 2:
        tvdi = np.full_like(ndvi, np.nan)
        _save_raster(output_path, tvdi, profile, dtype=rasterio.float32, nodata=-9999)
        return {"output_path": output_path, "warning": "Insufficient bins for TVDI regression."}

    # Regression lines
    slope_max, int_max, _, _, _ = linregress(bin_centers, lst_max_list)
    slope_min, int_min, _, _, _ = linregress(bin_centers, lst_min_list)

    lst_dry = ndvi * slope_max + int_max
    lst_wet = ndvi * slope_min + int_min

    denom = lst_dry - lst_wet
    denom[denom == 0] = 1e-6
    tvdi = (lst - lst_wet) / denom

    tvdi = np.clip(tvdi, 0, 1)
    tvdi[~valid_mask] = np.nan

    _save_raster(output_path, tvdi.astype(rasterio.float32), profile, dtype=rasterio.float32, nodata=-9999)
    return {"output_path": output_path}


def calc_snow_loss_stats_handler(arguments: Dict[str, Any], context: Any, account: Any) -> Dict[str, Any]:
    """Calculate percentage of extreme snow loss from a binary map (1=Loss)."""
    rasterio, np = _lazy_imports()

    binary_map_path = arguments["binary_map_path"]

    with rasterio.open(binary_map_path) as src:
        data = src.read(1)

    if data.size == 0:
        return {"percentage": 0.0}

    flat = data.flatten().astype(np.float32)
    valid = flat[np.isfinite(flat)]

    if valid.size == 0:
        return {"percentage": 0.0}

    loss_count = np.sum(valid == 1.0)
    percentage = float(loss_count / valid.size)

    return {"percentage": percentage, "total_pixels": int(valid.size), "loss_pixels": int(loss_count)}


# ------------------------------------------------------------------------------
# Raster Statistics & Arithmetic
# ------------------------------------------------------------------------------

def raster_stats_handler(arguments: Dict[str, Any], context: Any, account: Any) -> Dict[str, Any]:
    """
    Compute descriptive statistics for a single-band raster.
    Returns mean, std, min, max, median, sum (ignoring nodata/NaN).
    If `stat` is specified, returns only that statistic.
    """
    rasterio, np = _lazy_imports()

    input_path = arguments["input_path"]
    stat = arguments.get("stat")  # optional: "mean"|"std"|"min"|"max"|"median"|"sum"
    band = int(arguments.get("band", 1))

    with rasterio.open(input_path) as src:
        data = src.read(band).astype(np.float32)
        nodata = src.nodata

    flat = data.flatten()
    if nodata is not None:
        flat = flat[flat != nodata]
    flat = flat[np.isfinite(flat)]

    if flat.size == 0:
        return {"error": "No valid pixels found"}

    stats = {
        "mean":   float(np.nanmean(flat)),
        "std":    float(np.nanstd(flat, ddof=1)),
        "min":    float(np.nanmin(flat)),
        "max":    float(np.nanmax(flat)),
        "median": float(np.nanmedian(flat)),
        "sum":    float(np.nansum(flat)),
        "count":  int(flat.size),
    }

    if stat:
        if stat not in stats:
            raise ValueError(f"Unknown stat '{stat}'. Choose from: {list(stats.keys())}")
        return {stat: stats[stat]}
    return stats


def raster_diff_handler(arguments: Dict[str, Any], context: Any, account: Any) -> Dict[str, Any]:
    """Element-wise difference between two co-registered single-band rasters (A - B) → output GeoTIFF."""
    rasterio, np = _lazy_imports()

    path_a = arguments["path_a"]
    path_b = arguments["path_b"]
    output_path = arguments["output_path"]

    with rasterio.open(path_a) as src:
        band_a = src.read(1).astype(np.float32)
        profile = src.profile

    with rasterio.open(path_b) as src:
        band_b = src.read(1).astype(np.float32)

    diff = band_a - band_b
    _save_raster(output_path, diff, profile, dtype=rasterio.float32, nodata=-9999)
    return {"output_path": output_path}


def raster_average_handler(arguments: Dict[str, Any], context: Any, account: Any) -> Dict[str, Any]:
    """Pixel-wise average (mean) of multiple co-registered single-band rasters → output GeoTIFF."""
    rasterio, np = _lazy_imports()

    input_paths = arguments["input_paths"]
    output_path = arguments["output_path"]

    if not input_paths:
        raise ValueError("input_paths must contain at least one file")

    stack = []
    profile = None
    for p in input_paths:
        with rasterio.open(p) as src:
            stack.append(src.read(1).astype(np.float32))
            if profile is None:
                profile = src.profile

    avg = np.nanmean(np.stack(stack, axis=0), axis=0)
    _save_raster(output_path, avg, profile, dtype=rasterio.float32, nodata=-9999)
    return {"output_path": output_path}


def hotspot_percentage_handler(arguments: Dict[str, Any], context: Any, account: Any) -> Dict[str, Any]:
    """
    Compute the fraction of valid pixels (non-NaN, non-nodata) whose value
    exceeds a given threshold. Returns a ratio in [0.0, 1.0].
    """
    rasterio, np = _lazy_imports()

    input_path = arguments["input_path"]
    threshold = float(arguments["threshold"])

    with rasterio.open(input_path) as src:
        data = src.read(1).astype(np.float32)
        nodata = src.nodata

    flat = data.flatten()
    if nodata is not None:
        flat = flat[flat != nodata]
    valid = flat[np.isfinite(flat)]

    if valid.size == 0:
        return {"percentage": 0.0, "count_above": 0, "total_valid": 0}

    count_above = int(np.sum(valid > threshold))
    return {
        "percentage": float(count_above / valid.size),
        "count_above": count_above,
        "total_valid": int(valid.size),
    }


def apply_cloud_mask_handler(arguments: Dict[str, Any], context: Any, account: Any) -> Dict[str, Any]:
    """
    Apply a Landsat/Sentinel QA pixel band to mask cloud and cloud-shadow pixels.
    Masked pixels are set to nodata. Works with Landsat Collection 2 QA_PIXEL (bit 3=cloud, bit 4=shadow)
    and Sentinel-2 SCL band (values 3,8,9,10=cloud/shadow).
    """
    rasterio, np = _lazy_imports()

    sr_path = arguments["sr_path"]
    qa_path = arguments["qa_path"]
    output_path = arguments["output_path"]
    sensor = arguments.get("sensor", "landsat").lower()  # "landsat" or "sentinel2"

    with rasterio.open(sr_path) as src:
        band = src.read(1).astype(np.float32)
        profile = src.profile
        nodata_val = src.nodata if src.nodata is not None else -9999

    with rasterio.open(qa_path) as src:
        qa = src.read(1)

    if sensor == "sentinel2":
        # SCL: 3=cloud shadow, 8=medium cloud, 9=high cloud, 10=cirrus
        cloud_mask = np.isin(qa, [3, 8, 9, 10])
    else:
        # Landsat Collection 2 QA_PIXEL: bit3=cloud, bit4=cloud shadow
        cloud_mask = ((qa & (1 << 3)) > 0) | ((qa & (1 << 4)) > 0)

    band[cloud_mask] = nodata_val
    _save_raster(output_path, band, profile, dtype=rasterio.float32, nodata=nodata_val)

    masked_count = int(np.sum(cloud_mask))
    return {"output_path": output_path, "masked_pixels": masked_count}


def get_percentile_value_handler(arguments: Dict[str, Any], context: Any, account: Any) -> Dict[str, Any]:
    """Return the pixel value at a given percentile in a single-band raster (ignoring nodata/NaN)."""
    rasterio, np = _lazy_imports()

    input_path = arguments["input_path"]
    percentile = float(arguments["percentile"])
    band = int(arguments.get("band", 1))

    if not (0 <= percentile <= 100):
        raise ValueError("percentile must be in [0, 100]")

    with rasterio.open(input_path) as src:
        data = src.read(band).astype(np.float32)
        nodata = src.nodata

    flat = data.flatten()
    if nodata is not None:
        flat = flat[flat != nodata]
    valid = flat[np.isfinite(flat)]

    if valid.size == 0:
        return {"error": "No valid pixels found"}

    value = float(np.percentile(valid, percentile))
    return {"percentile": percentile, "value": value}


# ------------------------------------------------------------------------------
# Raster Utilities (Threshold, Counting, Skeletonization)
# ------------------------------------------------------------------------------

_OTSU_BINS = 256


def _otsu_threshold(values: Any, value_range: tuple) -> float:
    """Otsu threshold over a fixed histogram range, so results are reproducible."""
    _, np = _lazy_imports()
    clipped = np.clip(values, *value_range)
    counts, edges = np.histogram(clipped, bins=_OTSU_BINS, range=value_range)
    centers = (edges[:-1] + edges[1:]) / 2
    weight_low = np.cumsum(counts)
    weight_high = weight_low[-1] - weight_low
    sum_low = np.cumsum(counts * centers)
    mean_low = np.divide(sum_low, weight_low, out=np.zeros_like(sum_low), where=weight_low > 0)
    mean_high = np.divide(sum_low[-1] - sum_low, weight_high, out=np.zeros_like(sum_low), where=weight_high > 0)
    between = weight_low * weight_high * (mean_low - mean_high) ** 2
    # Empty bins between two modes form a plateau of equal variance; take its
    # middle rather than the edge hugging the lower mode.
    best = np.flatnonzero(between == between.max())
    return float(edges[int(round(float(best.mean()))) + 1])


def threshold_segmentation_handler(arguments: Dict[str, Any], context: Any, account: Any) -> Dict[str, Any]:
    """
    Binary threshold segmentation on a single-band raster image.

    Defaults keep the original behaviour: pixels > threshold → 255, others → 0,
    output nodata tag 0, no input masking. Optional arguments cover other
    scenarios without new tools:
      - direction: "above" (default) or "below" the threshold is foreground.
      - input_transform: "none" (default) or "db" (10·log10, values <= 0 invalid).
      - method: "fixed" (default) uses `threshold`; "otsu" derives it from the
        valid pixels over `otsu_range` (in transformed units).
      - foreground_value / background_value: output label values.
      - nodata_value: when set, input nodata, non-finite and transform-invalid
        pixels are written with this value and tagged as output nodata.
    """
    rasterio, np = _lazy_imports()

    input_path = arguments["input_path"]
    output_path = arguments["output_path"]
    direction = arguments.get("direction", "above")
    transform = arguments.get("input_transform", "none")
    method = arguments.get("method", "fixed")
    foreground = int(arguments.get("foreground_value", 255))
    background = int(arguments.get("background_value", 0))
    nodata_value = arguments.get("nodata_value")
    if direction not in ("above", "below"):
        raise ValueError("direction must be 'above' or 'below'")
    if transform not in ("none", "db"):
        raise ValueError("input_transform must be 'none' or 'db'")
    if method not in ("fixed", "otsu"):
        raise ValueError("method must be 'fixed' or 'otsu'")
    if method == "fixed" and arguments.get("threshold") is None:
        raise ValueError("threshold is required when method is 'fixed'")
    labels = {foreground, background} | ({int(nodata_value)} if nodata_value is not None else set())
    if min(labels) < 0 or max(labels) > 255 or len(labels) < (3 if nodata_value is not None else 2):
        raise ValueError("foreground, background and nodata values must be distinct integers in 0..255")

    with rasterio.open(input_path) as src:
        band = src.read(1, masked=nodata_value is not None)
        profile = src.profile
    if nodata_value is None:
        image = np.asarray(band, dtype=np.float64)
        valid = np.ones(image.shape, dtype=bool)
    else:
        image = np.ma.filled(band.astype(np.float64), np.nan)
        valid = ~np.ma.getmaskarray(band) & np.isfinite(image)
    if transform == "db":
        positive = image > 0
        if nodata_value is not None:
            valid &= positive
        image = np.where(positive, 10.0 * np.log10(np.where(positive, image, 1.0)), np.nan)

    valid_pixels = int(np.count_nonzero(valid))
    if valid_pixels == 0:
        return {
            "success": False,
            "execution_blocked": True,
            "reason_code": "no_valid_pixels",
            "failed_checks": ["no_valid_pixels"],
        }
    if method == "otsu":
        default_range = (-35.0, 5.0) if transform == "db" else None
        value_range = tuple(arguments.get("otsu_range") or default_range or (
            float(np.nanmin(image[valid])), float(np.nanmax(image[valid]))
        ))
        threshold = _otsu_threshold(image[valid], value_range)
    else:
        threshold = float(arguments["threshold"])

    with np.errstate(invalid="ignore"):
        hit = image > threshold if direction == "above" else image < threshold
    hit &= valid
    output = np.full(image.shape, background, dtype=np.uint8)
    output[hit] = foreground
    if nodata_value is not None:
        output[~valid] = int(nodata_value)

    _save_raster(
        output_path,
        output,
        profile,
        dtype=rasterio.uint8,
        nodata=int(nodata_value) if nodata_value is not None else 0,
    )
    foreground_pixels = int(np.count_nonzero(hit))
    return {
        "output_path": output_path,
        "method": method,
        "threshold": threshold,
        "direction": direction,
        "input_transform": transform,
        "label_values": {"foreground": foreground, "background": background, "nodata": nodata_value},
        "valid_pixels": valid_pixels,
        "foreground_pixels": foreground_pixels,
        "foreground_fraction": foreground_pixels / valid_pixels,
    }


def count_above_threshold_handler(arguments: Dict[str, Any], context: Any, account: Any) -> Dict[str, Any]:
    """Count pixels in a single-band raster whose values exceed a given threshold."""
    rasterio, np = _lazy_imports()

    input_path = arguments["input_path"]
    threshold = float(arguments["threshold"])

    with rasterio.open(input_path) as src:
        data = src.read(1).astype(np.float32)

    count = int(np.sum(data > threshold))
    return {"count": count}


def count_skeleton_contours_handler(arguments: Dict[str, Any], context: Any, account: Any) -> Dict[str, Any]:
    """
    Read a binary image, apply erosion and skeletonization,
    then count external contours in the skeletonized result.
    Requires: opencv-python-headless, scikit-image.
    """
    try:
        import cv2
        import numpy as np
        from skimage.morphology import skeletonize
    except ImportError:
        raise ImportError(
            "Missing dependencies for count_skeleton_contours. "
            "Install: pip install opencv-python-headless scikit-image"
        )

    image_path = arguments["image_path"]

    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise FileNotFoundError(f"Failed to read image: {image_path}")

    _, binary = cv2.threshold(img, 127, 255, cv2.THRESH_BINARY)

    kernel = np.ones((3, 3), np.uint8)
    eroded = cv2.erode(binary, kernel, iterations=1)

    skeleton = skeletonize(eroded > 0)
    skeleton_uint8 = (skeleton * 255).astype(np.uint8)

    contours, _ = cv2.findContours(skeleton_uint8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return {"count": len(contours)}


# ------------------------------------------------------------------------------
# Fire Monitoring Tools
# ------------------------------------------------------------------------------

def calculate_frp_handler(arguments: Dict[str, Any], context: Any, account: Any) -> Dict[str, Any]:
    """
    Generate a binary fire mask from a Fire Radiative Power (FRP) raster.
    Pixels with FRP > threshold (default 0) are marked as fire (255); others 0.
    Saves result as GeoTIFF and returns fire pixel count and coverage percentage.
    """
    rasterio, np = _lazy_imports()

    input_path = arguments["input_path"]
    output_path = arguments["output_path"]
    threshold = float(arguments.get("threshold", 0))

    with rasterio.open(input_path) as src:
        frp = src.read(1).astype(np.float32)
        profile = src.profile
        nodata = src.nodata

    valid_mask = np.isfinite(frp)
    if nodata is not None:
        valid_mask &= (frp != nodata)

    fire_mask = (valid_mask & (frp > threshold)).astype(np.uint8) * 255
    fire_count = int(np.sum(fire_mask > 0))
    total_valid = int(np.sum(valid_mask))

    _save_raster(output_path, fire_mask, profile, dtype=rasterio.uint8, nodata=0)

    return {
        "status": "success",
        "output_path": output_path,
        "fire_pixels": fire_count,
        "total_valid_pixels": total_valid,
        "fire_coverage": float(fire_count / total_valid) if total_valid > 0 else 0.0,
    }


def count_fire_pixels_handler(arguments: Dict[str, Any], context: Any, account: Any) -> Dict[str, Any]:
    """
    Count fire pixels in one or multiple rasters.
    For each input raster, count pixels exceeding the FRP threshold.
    Returns per-image counts and aggregate statistics.
    """
    rasterio, np = _lazy_imports()

    input_paths = arguments.get("input_paths") or [arguments.get("input_path")]
    input_paths = [p for p in input_paths if p]
    threshold = float(arguments.get("threshold", 0))

    if not input_paths:
        raise ValueError("Provide 'input_paths' (list) or 'input_path' (single file)")

    results = []
    total_fire = 0
    for p in input_paths:
        with rasterio.open(p) as src:
            data = src.read(1).astype(np.float32)
            nodata = src.nodata
        valid = np.isfinite(data)
        if nodata is not None:
            valid &= (data != nodata)
        count = int(np.sum(valid & (data > threshold)))
        results.append({"path": p, "fire_pixels": count, "valid_pixels": int(np.sum(valid))})
        total_fire += count

    return {
        "per_image": results,
        "total_fire_pixels": total_fire,
        "image_count": len(input_paths),
    }


def create_fire_increase_map_handler(arguments: Dict[str, Any], context: Any, account: Any) -> Dict[str, Any]:
    """
    Generate a temporal fire increase map: pixels where fire appeared (post=fire, pre=no fire).
    Inputs: binary fire masks (1=fire, 0=no fire) for two time steps.
    Output: binary map (255=fire increase, 0=no change or decrease).
    """
    rasterio, np = _lazy_imports()

    pre_path = arguments["pre_path"]
    post_path = arguments["post_path"]
    output_path = arguments["output_path"]
    threshold = float(arguments.get("threshold", 127))

    with rasterio.open(pre_path) as src:
        pre = src.read(1).astype(np.float32)
        profile = src.profile
    with rasterio.open(post_path) as src:
        post = src.read(1).astype(np.float32)

    pre_fire = pre > threshold
    post_fire = post > threshold
    increase = (~pre_fire & post_fire).astype(np.uint8) * 255

    _save_raster(output_path, increase, profile, dtype=rasterio.uint8, nodata=0)
    new_fire_count = int(np.sum(increase > 0))

    return {
        "status": "success",
        "output_path": output_path,
        "new_fire_pixels": new_fire_count,
    }


def get_raster_info_handler(arguments: Dict[str, Any], context: Any, account: Any) -> Dict[str, Any]:
    """Read raster metadata: CRS, GSD, pixel size, shape, band count, dtype, and tags."""
    import rasterio
    import math

    raster_path = arguments["raster_path"]
    try:
        with rasterio.open(raster_path) as src:
            tags = src.tags()
            # GSD priority: 1) explicit GSD tag (xBD pseudo-TIF), 2) pixel size in native units
            gsd_m = None
            if "GSD" in tags:
                try:
                    gsd_m = float(tags["GSD"])
                except (ValueError, TypeError):
                    pass

            if gsd_m is None:
                px = abs(src.transform.a)
                py = abs(src.transform.e)
                pixel_size_deg = (px + py) / 2.0
                if src.crs and src.crs.is_geographic:
                    # Degrees → metres (approximate, valid for mid-latitudes)
                    gsd_m = round(pixel_size_deg * 111320, 4)
                else:
                    # Projected CRS: pixel size already in metres
                    gsd_m = round(pixel_size_deg, 4)

            return {
                "status": "success",
                "width": src.width,
                "height": src.height,
                "band_count": src.count,
                "dtype": str(src.dtypes[0]),
                "crs": str(src.crs) if src.crs else None,
                "pixel_size_x": abs(src.transform.a),
                "pixel_size_y": abs(src.transform.e),
                "gsd_m": round(gsd_m, 4) if gsd_m is not None else None,
                "tags": tags,
                "is_pseudo_geotiff": tags.get("IS_PSEUDO_GEOTIFF", "FALSE") == "TRUE",
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def identify_fire_prone_areas_handler(arguments: Dict[str, Any], context: Any, account: Any) -> Dict[str, Any]:
    """
    Identify fire-prone areas as pixels in the top percentile of FRP values across a time series.
    Input: list of FRP rasters. Output: binary mask where 255=high fire risk area.
    """
    rasterio, np = _lazy_imports()

    input_paths = arguments.get("input_paths", [])
    output_path = arguments["output_path"]
    percentile = float(arguments.get("percentile", 90))

    if not input_paths:
        raise ValueError("input_paths must contain at least one file path")

    all_values = []
    profile = None
    shapes = []
    for p in input_paths:
        with rasterio.open(p) as src:
            d = src.read(1).astype(np.float32)
            nd = src.nodata
            if profile is None:
                profile = src.profile
            shapes.append(d.shape)
        valid = d.flatten()
        if nd is not None:
            valid = valid[valid != nd]
        all_values.append(valid[np.isfinite(valid)])

    # Compute threshold from combined distribution
    combined = np.concatenate(all_values)
    if combined.size == 0:
        return {"status": "error", "message": "No valid pixels found"}

    threshold_value = float(np.percentile(combined, percentile))

    # Create mean FRP raster and threshold it
    # Use first raster as reference shape
    ref_shape = shapes[0]
    stack = []
    for p in input_paths:
        with rasterio.open(p) as src:
            d = src.read(1).astype(np.float32)
        if d.shape != ref_shape:
            continue
        stack.append(d)

    mean_frp = np.nanmean(np.stack(stack, axis=0), axis=0) if stack else np.zeros(ref_shape)
    prone_mask = (mean_frp > threshold_value).astype(np.uint8) * 255

    _save_raster(output_path, prone_mask, profile, dtype=rasterio.uint8, nodata=0)
    prone_count = int(np.sum(prone_mask > 0))

    return {
        "status": "success",
        "output_path": output_path,
        "frp_threshold": threshold_value,
        "prone_pixels": prone_count,
        "percentile_used": percentile,
    }


# ------------------------------------------------------------------------------
# Registration
# ------------------------------------------------------------------------------

def setup(registrar):
    """Register all raster calculation tools."""
    registrar.toolkit(
        name="geo_raster",
        description="Raster analysis: spectral indices (NDVI/NDWI/EVI/FVC/TVDI), fire monitoring (FRP, fire pixel detection, spread mapping), raster statistics (diff, average, percentile, hotspot), cloud masking, threshold segmentation, and snow loss analysis.",
        version="0.2.0"
    )

    # 1. Universal Index Calculator
    registrar.tool(
        ToolSpec(
            slug="geo_raster.calculate_index",
            name="Calculate Spectral Index",
            description="Calculate generic normalized difference indices like NDVI, NDWI, NDBI, NBR, NDTI, NDSI.",
            parameters={
                "type": "object",
                "properties": {
                    "band_a_path": {"type": "string", "description": "Path to the first band (e.g., NIR for NDVI)."},
                    "band_b_path": {"type": "string", "description": "Path to the second band (e.g., Red for NDVI)."},
                    "output_path": {"type": "string", "description": "Output GeoTIFF path."},
                    "index_name": {"type": "string", "description": "Name of index for logging (default: INDEX)."},
                    "scale_factor": {"type": "number", "description": "Optional scaling factor (default: 1.0)."}
                },
                "required": ["band_a_path", "band_b_path", "output_path"]
            },
            requires_connection=False
        ),
        calculate_normalized_difference_handler,
    )

    # 2. EVI
    registrar.tool(
        ToolSpec(
            slug="geo_raster.calculate_evi",
            name="Calculate EVI",
            description="Calculate Enhanced Vegetation Index (EVI). Requires NIR, Red, Blue bands.",
            parameters={
                "type": "object",
                "properties": {
                    "nir_path": {"type": "string", "description": "Path to NIR band."},
                    "red_path": {"type": "string", "description": "Path to Red band."},
                    "blue_path": {"type": "string", "description": "Path to Blue band."},
                    "output_path": {"type": "string", "description": "Output GeoTIFF path."},
                    "G": {"type": "number", "default": 2.5},
                    "C1": {"type": "number", "default": 6.0},
                    "C2": {"type": "number", "default": 7.5},
                    "L": {"type": "number", "default": 1.0}
                },
                "required": ["nir_path", "red_path", "blue_path", "output_path"]
            },
            requires_connection=False
        ),
        calculate_evi_handler,
    )

    # 3. FVC
    registrar.tool(
        ToolSpec(
            slug="geo_raster.calculate_fvc",
            name="Calculate FVC",
            description="Calculate Fractional Vegetation Cover (FVC) from NIR and Red bands.",
            parameters={
                "type": "object",
                "properties": {
                    "nir_path": {"type": "string", "description": "Path to NIR band."},
                    "red_path": {"type": "string", "description": "Path to Red band."},
                    "output_path": {"type": "string", "description": "Output GeoTIFF path."},
                    "ndvi_min": {"type": "number", "default": 0.1},
                    "ndvi_max": {"type": "number", "default": 0.9}
                },
                "required": ["nir_path", "red_path", "output_path"]
            },
            requires_connection=False
        ),
        calculate_fvc_handler,
    )

    # 4. WRI
    registrar.tool(
        ToolSpec(
            slug="geo_raster.calculate_wri",
            name="Calculate WRI",
            description="Calculate Water Ratio Index (WRI). Requires Green, Red, NIR, SWIR bands.",
            parameters={
                "type": "object",
                "properties": {
                    "green_path": {"type": "string"},
                    "red_path": {"type": "string"},
                    "nir_path": {"type": "string"},
                    "swir_path": {"type": "string"},
                    "output_path": {"type": "string"}
                },
                "required": ["green_path", "red_path", "nir_path", "swir_path", "output_path"]
            },
            requires_connection=False
        ),
        calculate_wri_handler,
    )

    # 5. TVDI
    registrar.tool(
        ToolSpec(
            slug="geo_raster.compute_tvdi",
            name="Compute TVDI",
            description="Compute Temperature Vegetation Dryness Index (TVDI) from NDVI and LST.",
            parameters={
                "type": "object",
                "properties": {
                    "ndvi_path": {"type": "string", "description": "Path to NDVI raster."},
                    "lst_path": {"type": "string", "description": "Path to LST raster."},
                    "output_path": {"type": "string", "description": "Output GeoTIFF path."}
                },
                "required": ["ndvi_path", "lst_path", "output_path"]
            },
            requires_connection=False
        ),
        compute_tvdi_handler,
    )

    # 7. Snow Stats
    registrar.tool(
        ToolSpec(
            slug="geo_raster.calc_snow_loss_stats",
            name="Calculate Snow Loss Stats",
            description="Calculate percentage of extreme snow loss from a binary map.",
            parameters={
                "type": "object",
                "properties": {
                    "binary_map_path": {"type": "string", "description": "Path to binary raster (1=loss)."}
                },
                "required": ["binary_map_path"]
            },
            requires_connection=False
        ),
        calc_snow_loss_stats_handler,
    )

    # 8. Threshold Segmentation
    registrar.tool(
        ToolSpec(
            slug="geo_raster.threshold_segmentation",
            name="Threshold Segmentation",
            description="Binary threshold segmentation on a single-band raster. By default pixels > threshold → 255 and others → 0 (e.g. FRP hotspot masks). Optional direction, dB transform, Otsu threshold, label values and nodata handling cover masks such as low-backscatter SAR water.",
            parameters={
                "type": "object",
                "properties": {
                    "input_path": {"type": "string", "description": "Path to input single-band raster."},
                    "threshold": {"type": "number", "description": "Threshold in transformed units; required unless method is 'otsu'."},
                    "output_path": {"type": "string", "description": "Output GeoTIFF path for binary mask."},
                    "direction": {"type": "string", "enum": ["above", "below"], "default": "above", "description": "Which side of the threshold is foreground."},
                    "input_transform": {"type": "string", "enum": ["none", "db"], "default": "none", "description": "Apply 10*log10 before thresholding."},
                    "method": {"type": "string", "enum": ["fixed", "otsu"], "default": "fixed"},
                    "otsu_range": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2, "description": "Histogram range for Otsu, in transformed units."},
                    "foreground_value": {"type": "integer", "default": 255, "minimum": 0, "maximum": 255},
                    "background_value": {"type": "integer", "default": 0, "minimum": 0, "maximum": 255},
                    "nodata_value": {"type": "integer", "minimum": 0, "maximum": 255, "description": "When set, invalid input pixels get this value and it is tagged as nodata."}
                },
                "required": ["input_path", "output_path"]
            },
            requires_connection=False
        ),
        threshold_segmentation_handler,
    )

    # 9. Count Above Threshold
    registrar.tool(
        ToolSpec(
            slug="geo_raster.count_above_threshold",
            name="Count Pixels Above Threshold",
            description="Count the number of pixels in a single-band raster whose values exceed a given threshold.",
            parameters={
                "type": "object",
                "properties": {
                    "input_path": {"type": "string", "description": "Path to input raster (GeoTIFF or raster format)."},
                    "threshold": {"type": "number", "description": "Threshold value; pixels strictly greater than this are counted."}
                },
                "required": ["input_path", "threshold"]
            },
            requires_connection=False
        ),
        count_above_threshold_handler,
    )

    # 10. Count Skeleton Contours
    registrar.tool(
        ToolSpec(
            slug="geo_raster.count_skeleton_contours",
            name="Count Skeleton Contours",
            description="Apply erosion and skeletonization to a binary image, then count external contours. Useful for counting elongated or network-like objects.",
            parameters={
                "type": "object",
                "properties": {
                    "image_path": {"type": "string", "description": "Path to input binary (black-and-white) image."}
                },
                "required": ["image_path"]
            },
            requires_connection=False
        ),
        count_skeleton_contours_handler,
    )

    # 11. Raster Stats
    registrar.tool(
        ToolSpec(
            slug="geo_raster.raster_stats",
            name="Raster Statistics",
            description="Compute descriptive statistics (mean, std, min, max, median, sum) for a single-band raster, ignoring nodata and NaN. Use `stat` to request only one statistic.",
            parameters={
                "type": "object",
                "properties": {
                    "input_path": {"type": "string", "description": "Path to input raster."},
                    "band": {"type": "integer", "default": 1, "description": "Band index (1-based). Default 1."},
                    "stat": {
                        "type": "string",
                        "enum": ["mean", "std", "min", "max", "median", "sum", "count"],
                        "description": "Optional: return only this statistic. Omit to return all."
                    }
                },
                "required": ["input_path"]
            },
            requires_connection=False
        ),
        raster_stats_handler,
    )

    # 12. Raster Diff
    registrar.tool(
        ToolSpec(
            slug="geo_raster.raster_diff",
            name="Raster Difference",
            description="Compute element-wise difference (A - B) between two co-registered single-band rasters and save the result as a GeoTIFF.",
            parameters={
                "type": "object",
                "properties": {
                    "path_a": {"type": "string", "description": "Path to raster A (minuend)."},
                    "path_b": {"type": "string", "description": "Path to raster B (subtrahend)."},
                    "output_path": {"type": "string", "description": "Output GeoTIFF path."}
                },
                "required": ["path_a", "path_b", "output_path"]
            },
            requires_connection=False
        ),
        raster_diff_handler,
    )

    # 13. Raster Average
    registrar.tool(
        ToolSpec(
            slug="geo_raster.raster_average",
            name="Raster Average",
            description="Compute the pixel-wise mean of multiple co-registered single-band rasters and save as a GeoTIFF.",
            parameters={
                "type": "object",
                "properties": {
                    "input_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of input raster file paths (must be co-registered, same extent/resolution)."
                    },
                    "output_path": {"type": "string", "description": "Output GeoTIFF path."}
                },
                "required": ["input_paths", "output_path"]
            },
            requires_connection=False
        ),
        raster_average_handler,
    )

    # 14. Hotspot Percentage
    registrar.tool(
        ToolSpec(
            slug="geo_raster.hotspot_percentage",
            name="Hotspot Percentage",
            description="Compute the fraction of valid pixels (non-NaN, non-nodata) exceeding a threshold. Returns ratio in [0.0, 1.0]. Useful for fire hotspot area estimation, flood extent ratio, etc.",
            parameters={
                "type": "object",
                "properties": {
                    "input_path": {"type": "string", "description": "Path to input raster."},
                    "threshold": {"type": "number", "description": "Pixels strictly greater than this value are counted as hotspots."}
                },
                "required": ["input_path", "threshold"]
            },
            requires_connection=False
        ),
        hotspot_percentage_handler,
    )

    # 15. Apply Cloud Mask
    registrar.tool(
        ToolSpec(
            slug="geo_raster.apply_cloud_mask",
            name="Apply Cloud Mask",
            description="Mask cloud and cloud-shadow pixels in a surface reflectance band using a Landsat QA_PIXEL band (bit3=cloud, bit4=shadow) or Sentinel-2 SCL band (values 3/8/9/10). Masked pixels are set to nodata.",
            parameters={
                "type": "object",
                "properties": {
                    "sr_path": {"type": "string", "description": "Path to input surface reflectance band."},
                    "qa_path": {"type": "string", "description": "Path to QA pixel / SCL band raster."},
                    "output_path": {"type": "string", "description": "Output masked GeoTIFF path."},
                    "sensor": {
                        "type": "string",
                        "enum": ["landsat", "sentinel2"],
                        "default": "landsat",
                        "description": "Sensor type controlling QA interpretation. Default: 'landsat'."
                    }
                },
                "required": ["sr_path", "qa_path", "output_path"]
            },
            requires_connection=False
        ),
        apply_cloud_mask_handler,
    )

    # 16. Get Percentile Value
    registrar.tool(
        ToolSpec(
            slug="geo_raster.get_percentile_value",
            name="Get Percentile Value",
            description="Return the pixel value at a given percentile (0–100) from a single-band raster, ignoring nodata and NaN.",
            parameters={
                "type": "object",
                "properties": {
                    "input_path": {"type": "string", "description": "Path to input raster."},
                    "percentile": {"type": "number", "description": "Percentile in [0, 100], e.g. 75 for the 75th percentile."},
                    "band": {"type": "integer", "default": 1, "description": "Band index (1-based). Default 1."}
                },
                "required": ["input_path", "percentile"]
            },
            requires_connection=False
        ),
        get_percentile_value_handler,
    )

    # 17. Calculate FRP
    registrar.tool(
        ToolSpec(
            slug="geo_raster.calculate_frp",
            name="Calculate Fire Radiative Power Mask",
            description="Generate a binary fire mask from a Fire Radiative Power (FRP) raster. Pixels exceeding the threshold are marked as fire (255). Returns fire pixel count and coverage percentage.",
            parameters={
                "type": "object",
                "properties": {
                    "input_path": {"type": "string", "description": "Path to input FRP raster (GeoTIFF)."},
                    "output_path": {"type": "string", "description": "Output path for binary fire mask GeoTIFF."},
                    "threshold": {"type": "number", "default": 0, "description": "FRP threshold above which a pixel is classified as fire (default: 0)."}
                },
                "required": ["input_path", "output_path"]
            },
            requires_connection=False
        ),
        calculate_frp_handler,
    )

    # 18. Count fire pixels
    registrar.tool(
        ToolSpec(
            slug="geo_raster.count_fire_pixels",
            name="Count Fire Pixels",
            description="Count the number of fire pixels (FRP > threshold) in one or multiple rasters. Returns per-image counts and aggregate total.",
            parameters={
                "type": "object",
                "properties": {
                    "input_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of FRP raster file paths to analyze."
                    },
                    "input_path": {"type": "string", "description": "Single FRP raster path (use instead of input_paths for one file)."},
                    "threshold": {"type": "number", "default": 0, "description": "FRP threshold above which a pixel is counted as fire (default: 0)."}
                },
                "required": []
            },
            requires_connection=False
        ),
        count_fire_pixels_handler,
    )

    # 19. Create fire increase map
    registrar.tool(
        ToolSpec(
            slug="geo_raster.create_fire_increase_map",
            name="Create Fire Increase Map",
            description="Detect pixels where fire appeared between two time steps (pre and post binary fire masks). Output is a binary GeoTIFF (255=new fire, 0=no new fire).",
            parameters={
                "type": "object",
                "properties": {
                    "pre_path": {"type": "string", "description": "Path to pre-event binary fire mask (1=fire or 255=fire)."},
                    "post_path": {"type": "string", "description": "Path to post-event binary fire mask (1=fire or 255=fire)."},
                    "output_path": {"type": "string", "description": "Output path for fire increase map GeoTIFF."},
                    "threshold": {"type": "number", "default": 127, "description": "Pixel value threshold to classify as 'fire' in input masks (default: 127)."}
                },
                "required": ["pre_path", "post_path", "output_path"]
            },
            requires_connection=False
        ),
        create_fire_increase_map_handler,
    )

    # 20. Identify fire-prone areas
    registrar.tool(
        ToolSpec(
            slug="geo_raster.identify_fire_prone_areas",
            name="Identify Fire-Prone Areas",
            description="Identify high fire-risk areas as pixels in the top N percentile of FRP values across a time series. Returns a binary mask (255=fire-prone area).",
            parameters={
                "type": "object",
                "properties": {
                    "input_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Time series of FRP raster file paths."
                    },
                    "output_path": {"type": "string", "description": "Output path for fire-prone area mask GeoTIFF."},
                    "percentile": {"type": "number", "default": 90, "description": "Percentile threshold for fire-prone classification (default: 90 = top 10% of values)."}
                },
                "required": ["input_paths", "output_path"]
            },
            requires_connection=False
        ),
        identify_fire_prone_areas_handler,
    )

    # 17. Get Raster Info
    registrar.tool(
        ToolSpec(
            slug="geo_raster.get_raster_info",
            name="Get Raster Info",
            description="Read raster metadata: CRS, GSD (metres/pixel), pixel size, image dimensions, band count, data type, and embedded tags (e.g. IS_PSEUDO_GEOTIFF, GSD). Use this as the first step whenever the GSD of the input image is unknown.",
            parameters={
                "type": "object",
                "properties": {
                    "raster_path": {"type": "string", "description": "Path to the input raster file (GeoTIFF or any GDAL-readable format)."}
                },
                "required": ["raster_path"]
            },
            requires_connection=False
        ),
        get_raster_info_handler,
    )