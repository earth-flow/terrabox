"""
geopatch toolkit
----------------
A thin wrapper around the open-source project "GeoPatch" (MIT) by Hejar Shahabi,
exposing its core patch-generation utilities as callable tools in your platform.

Repository (please keep attribution in your product/docs):
- https://github.com/Hejarshahabi/GeoPatch  (MIT License)

This toolkit provides:
1) geopatch.train_init     - Initialize TrainPatch with image and (optional) labels (raster or shapefile)
2) geopatch.train_info     - Echo basic TrainPatch status/config
3) geopatch.generate_seg   - Generate patches for semantic segmentation (TIFF or NumPy)
4) geopatch.generate_det   - Generate patches for object detection (YOLO labels; optional seg masks)
5) geopatch.visualize      - Visualize saved patches (matplotlib-based)
6) geopatch.pred_init      - Initialize PredictionPatch for inference tiling
7) geopatch.pred_save_tif  - Save prediction tiles as GeoTIFF
8) geopatch.pred_save_npy  - Save prediction tiles as NumPy arrays

Notes:
- This is a thin orchestration layer. All heavy lifting is done by GeoPatch.
- Handlers keep arguments close to the original GeoPatch API for minimal friction.
- A simple per-session in-memory cache holds TrainPatch/PredictionPatch instances.

Usage:
- Ensure GeoPatch is installed in production: `pip install GeoPatch`
- Keep repository attribution in your product per MIT license terms.

"""

from __future__ import annotations
from typing import Any, Dict, Optional
import os

from ..core.registry import ToolSpec

# Lazy import flags and references; this allows test stubs or deferred errors.
_HAS_GEOPATCH = False
_TrainPatch = None
_PredictionPatch = None

def _ensure_geopatch():
    """Import GeoPatch only when needed; raise a helpful error if missing."""
    global _HAS_GEOPATCH, _TrainPatch, _PredictionPatch
    if _HAS_GEOPATCH and _TrainPatch and _PredictionPatch:
        return

    try:
        from GeoPatch import TrainPatch, PredictionPatch  # type: ignore
        _HAS_GEOPATCH = True
        _TrainPatch = TrainPatch
        _PredictionPatch = PredictionPatch
    except Exception as e:
        raise ImportError(
            "GeoPatch is required for this toolkit. Install with: pip install GeoPatch\n"
            "Original repository: https://github.com/Hejarshahabi/GeoPatch\n"
            f"Import error: {e}"
        )


# ------------------------------------------------------------------------------
# Simple per-session cache (replace with your platform's session store if needed)
# ------------------------------------------------------------------------------
_SESSIONS: Dict[str, Dict[str, Any]] = {}

def _get_session(context: Dict[str, Any]) -> Dict[str, Any]:
    """Return a per-session dict using session_id or user_id as key."""
    sid = context.get("session_id") or context.get("user_id") or "default"
    if sid not in _SESSIONS:
        _SESSIONS[sid] = {}
    return _SESSIONS[sid]


# ------------------------------------------------------------------------------
# Handlers
# ------------------------------------------------------------------------------

def gp_train_init_handler(arguments: dict, context: dict, account=None):
    """
    Initialize a TrainPatch object.

    Parameters
    ----------
    image : str | numpy.ndarray
        Path to image (.tif/.npy) or a numpy array.
    label : str | numpy.ndarray | None
        Optional path to label (.tif/.npy) or a numpy array.
    patch_size : int, default 128
    stride : int, default patch_size
    channel_first : bool, default True
    shapefile_path : str | None
        Optional polygon shapefile for labels.
    label_field : str | None
        Integer class field name in the shapefile.

    Returns a summary dict and stores the TrainPatch in the session cache.
    """
    _ensure_geopatch()
    sess = _get_session(context)

    image = arguments.get("image")
    label = arguments.get("label")
    patch_size = int(arguments.get("patch_size", 128))
    stride = int(arguments.get("stride", patch_size))
    channel_first = bool(arguments.get("channel_first", True))
    shapefile_path = arguments.get("shapefile_path")
    label_field = arguments.get("label_field")

    if image is None:
        raise ValueError("Missing 'image' (path or numpy array).")

    patch = _TrainPatch(
        image=image,
        label=label,
        patch_size=patch_size,
        stride=stride,
        channel_first=channel_first,
        shapefile_path=shapefile_path,
        label_field=label_field
    )
    sess["geopatch_train"] = patch

    return {
        "status": "initialized",
        "config": {
            "patch_size": patch_size,
            "stride": stride,
            "channel_first": channel_first,
            "image": str(image) if isinstance(image, str) else "numpy",
            "label": (str(label) if isinstance(label, str)
                      else ("numpy" if label is not None else None)),
            "shapefile_path": shapefile_path,
            "label_field": label_field
        },
        "note": "TrainPatch is ready for generate_seg / generate_det / visualize.",
        "reference": {
            "repo": "https://github.com/Hejarshahabi/GeoPatch",
            "license": "MIT"
        }
    }


def gp_train_info_handler(arguments: dict, context: dict, account=None):
    """
    Echo a minimal status/config for the current TrainPatch in session.
    Useful for orchestration sanity checks.
    """
    _ensure_geopatch()
    sess = _get_session(context)
    patch = sess.get("geopatch_train")
    if patch is None:
        raise RuntimeError("TrainPatch is not initialized. Call geopatch.train_init first.")
    return {
        "status": "ok",
        "hint": "TrainPatch is present in session. Use generate_seg / generate_det / visualize next."
    }


def gp_generate_seg_handler(arguments: dict, context: dict, account=None):
    """
    Generate segmentation patches (image + label).

    Parameters (aligned with GeoPatch):
    - format : "tif" | "npy" (default "tif")
      * augmentations (V_flip/H_flip/Rotation) apply to "npy" per GeoPatch design.
    - folder_name : str (default "seg_patches")
    - only_label : bool (default True)
    - return_stacked : bool (default False; "npy" only)
    - save_stack : bool (default False; "npy" only)
    - V_flip / H_flip / Rotation : bool (augmentations; "npy" only)
    """
    _ensure_geopatch()
    sess = _get_session(context)
    patch = sess.get("geopatch_train")
    if patch is None:
        raise RuntimeError("TrainPatch is not initialized. Call geopatch.train_init first.")

    fmt = (arguments.get("format") or "tif").lower()
    folder = arguments.get("folder_name") or "seg_patches"
    only_label = bool(arguments.get("only_label", True))
    return_stacked = bool(arguments.get("return_stacked", False))
    save_stack = bool(arguments.get("save_stack", False))
    V_flip = bool(arguments.get("V_flip", False))
    H_flip = bool(arguments.get("H_flip", False))
    Rotation = bool(arguments.get("Rotation", False))

    os.makedirs(folder, exist_ok=True)

    if fmt == "npy":
        out = patch.generate_segmentation(
            format="npy",
            folder_name=folder,
            only_label=only_label,
            return_stacked=return_stacked,
            save_stack=save_stack,
            V_flip=V_flip,
            H_flip=H_flip,
            Rotation=Rotation
        )
        returned = isinstance(out, (tuple, list))
    else:
        patch.generate_segmentation(
            format="tif",
            folder_name=folder,
            only_label=only_label,
            return_stacked=False,
            save_stack=False,
            V_flip=False,
            H_flip=False,
            Rotation=False
        )
        returned = False

    return {
        "status": "done",
        "format": fmt,
        "output_dir": os.path.abspath(folder),
        "returned_numpy": returned,
        "note": "Augmentations apply only when format='npy' per GeoPatch.",
        "reference": {"repo": "https://github.com/Hejarshahabi/GeoPatch"}
    }


def gp_generate_det_handler(arguments: dict, context: dict, account=None):
    """
    Generate detection patches (YOLO txt labels; optional segmentation masks).

    Parameters (aligned with GeoPatch):
    - format : "tif" | "npy" (default "npy")
    - folder_name : str (default "det_patches")
    - only_label : bool (default True)
    - return_stacked / save_stack : bool (effective for "npy")
    - V_flip / H_flip / Rotation : bool (augmentations; effective for "npy")
    - segmentation : bool (default True) - also produce segmentation masks
    """
    _ensure_geopatch()
    sess = _get_session(context)
    patch = sess.get("geopatch_train")
    if patch is None:
        raise RuntimeError("TrainPatch is not initialized. Call geopatch.train_init first.")

    fmt = (arguments.get("format") or "npy").lower()
    folder = arguments.get("folder_name") or "det_patches"
    only_label = bool(arguments.get("only_label", True))
    return_stacked = bool(arguments.get("return_stacked", False))
    save_stack = bool(arguments.get("save_stack", False))
    V_flip = bool(arguments.get("V_flip", False))
    H_flip = bool(arguments.get("H_flip", False))
    Rotation = bool(arguments.get("Rotation", False))
    segmentation = bool(arguments.get("segmentation", True))

    os.makedirs(folder, exist_ok=True)

    out = patch.generate_detection(
        format=fmt,
        folder_name=folder,
        only_label=only_label,
        return_stacked=return_stacked,
        save_stack=save_stack,
        V_flip=V_flip,
        H_flip=H_flip,
        Rotation=Rotation,
        segmentation=segmentation
    )
    returned = isinstance(out, (tuple, list))

    return {
        "status": "done",
        "format": fmt,
        "output_dir": os.path.abspath(folder),
        "returned_numpy": returned,
        "yolo_labels": True,
        "note": "YOLO .txt annotations are emitted for detection mode.",
        "reference": {"repo": "https://github.com/Hejarshahabi/GeoPatch"}
    }


def gp_visualize_handler(arguments: dict, context: dict, account=None):
    """
    Visualize saved patches (delegates to GeoPatch's matplotlib viewer).

    Parameters:
    - folder_name : str, default "seg_patches"
    - patches_to_show : int, default 2
    - band_num : int, default 1
    - fig_size : tuple (w, h), default (10, 20)
    - dpi : int, default 96
    - show_bboxes : bool, default False
    """
    _ensure_geopatch()
    sess = _get_session(context)
    patch = sess.get("geopatch_train")
    if patch is None:
        raise RuntimeError("TrainPatch is not initialized. Call geopatch.train_init first.")

    folder = arguments.get("folder_name") or "seg_patches"
    patches_to_show = int(arguments.get("patches_to_show", 2))
    band_num = int(arguments.get("band_num", 1))
    fig_size = tuple(arguments.get("fig_size", (10, 20)))
    dpi = int(arguments.get("dpi", 96))
    show_bboxes = bool(arguments.get("show_bboxes", False))

    patch.visualize(
        folder_name=folder,
        patches_to_show=patches_to_show,
        band_num=band_num,
        fig_size=fig_size,
        dpi=dpi,
        show_bboxes=show_bboxes
    )

    return {
        "status": "rendered",
        "folder": os.path.abspath(folder),
        "note": "Visualization rendered via GeoPatch (matplotlib)."
    }


def gp_pred_init_handler(arguments: dict, context: dict, account=None):
    """
    Initialize a PredictionPatch for inference tiling.

    Parameters
    ----------
    image : str | numpy.ndarray
        Path to image (.tif/.npy) or numpy array.
    patch_size : int, default 128
    stride : int, default patch_size
    channel_first : bool, default True
    """
    _ensure_geopatch()
    sess = _get_session(context)

    image = arguments.get("image")
    if image is None:
        raise ValueError("Missing 'image'.")

    patch_size = int(arguments.get("patch_size", 128))
    stride = int(arguments.get("stride", patch_size))
    channel_first = bool(arguments.get("channel_first", True))

    pred = _PredictionPatch(
        image=image,
        patch_size=patch_size,
        stride=stride,
        channel_first=channel_first
    )
    sess["geopatch_pred"] = pred

    return {
        "status": "initialized",
        "config": {
            "patch_size": patch_size,
            "stride": stride,
            "channel_first": channel_first,
            "image": str(image) if isinstance(image, str) else "numpy"
        },
        "reference": {"repo": "https://github.com/Hejarshahabi/GeoPatch"}
    }


def gp_pred_save_tif_handler(arguments: dict, context: dict, account=None):
    """
    Save prediction tiles as GeoTIFFs into a folder.
    """
    _ensure_geopatch()
    sess = _get_session(context)
    pred = sess.get("geopatch_pred")
    if pred is None:
        raise RuntimeError("PredictionPatch is not initialized. Call geopatch.pred_init first.")

    folder = arguments.get("folder_name") or "pred_tif"
    os.makedirs(folder, exist_ok=True)
    pred.save_Geotif(folder_name=folder)

    return {"status": "done", "format": "tif", "output_dir": os.path.abspath(folder)}


def gp_pred_save_npy_handler(arguments: dict, context: dict, account=None):
    """
    Save prediction tiles as NumPy arrays into a folder.
    """
    _ensure_geopatch()
    sess = _get_session(context)
    pred = sess.get("geopatch_pred")
    if pred is None:
        raise RuntimeError("PredictionPatch is not initialized. Call geopatch.pred_init first.")

    folder = arguments.get("folder_name") or "pred_npy"
    os.makedirs(folder, exist_ok=True)
    pred.save_numpy(folder_name=folder)

    return {"status": "done", "format": "npy", "output_dir": os.path.abspath(folder)}


# ------------------------------------------------------------------------------
# Registration
# ------------------------------------------------------------------------------
def setup(registrar):
    """Register the toolkit and tools with the platform (same style as your example)."""
    registrar.toolkit(
        name="geopatch",
        description="Wrapper tools for GeoPatch (MIT): training and prediction patch generation for geospatial rasters.",
        version="1.0.0"
    )

    # 1) Train init
    registrar.tool(
        ToolSpec(
            slug="geopatch.train_init",
            name="GeoPatch Train Init",
            description="Initialize TrainPatch with image and optional raster/shapefile labels.",
            parameters={
                "type": "object",
                "properties": {
                    "image": {"description": "Path to .tif/.npy image or numpy array"},
                    "label": {"description": "Optional path to .tif/.npy label or numpy array"},
                    "patch_size": {"type": "integer", "default": 128},
                    "stride": {"type": "integer", "default": 128},
                    "channel_first": {"type": "boolean", "default": True},
                    "shapefile_path": {"type": "string", "description": "Optional polygon shapefile for labels"},
                    "label_field": {"type": "string", "description": "Integer class field in shapefile"}
                },
                "required": ["image"]
            },
            requires_connection=False
        ),
        gp_train_init_handler
    )

    # 2) Train info
    registrar.tool(
        ToolSpec(
            slug="geopatch.train_info",
            name="GeoPatch Train Info",
            description="Echo TrainPatch status/config.",
            parameters={"type": "object", "properties": {}, "required": []},
            requires_connection=False
        ),
        gp_train_info_handler
    )

    # 3) Generate segmentation patches
    registrar.tool(
        ToolSpec(
            slug="geopatch.generate_seg",
            name="GeoPatch Generate Segmentation",
            description="Generate segmentation patches (GeoTIFF or NumPy).",
            parameters={
                "type": "object",
                "properties": {
                    "format": {"type": "string", "enum": ["tif", "npy"], "default": "tif"},
                    "folder_name": {"type": "string", "default": "seg_patches"},
                    "only_label": {"type": "boolean", "default": True},
                    "return_stacked": {"type": "boolean", "default": False},
                    "save_stack": {"type": "boolean", "default": False},
                    "V_flip": {"type": "boolean", "default": False},
                    "H_flip": {"type": "boolean", "default": False},
                    "Rotation": {"type": "boolean", "default": False}
                },
                "required": []
            },
            requires_connection=False
        ),
        gp_generate_seg_handler
    )

    # 4) Generate detection patches
    registrar.tool(
        ToolSpec(
            slug="geopatch.generate_det",
            name="GeoPatch Generate Detection (YOLO)",
            description="Generate detection patches with YOLO .txt labels; optional segmentation masks.",
            parameters={
                "type": "object",
                "properties": {
                    "format": {"type": "string", "enum": ["tif", "npy"], "default": "npy"},
                    "folder_name": {"type": "string", "default": "det_patches"},
                    "only_label": {"type": "boolean", "default": True},
                    "return_stacked": {"type": "boolean", "default": False},
                    "save_stack": {"type": "boolean", "default": False},
                    "V_flip": {"type": "boolean", "default": False},
                    "H_flip": {"type": "boolean", "default": False},
                    "Rotation": {"type": "boolean", "default": False},
                    "segmentation": {"type": "boolean", "default": True}
                },
                "required": []
            },
            requires_connection=False
        ),
        gp_generate_det_handler
    )

    # 5) Visualize
    registrar.tool(
        ToolSpec(
            slug="geopatch.visualize",
            name="GeoPatch Visualize",
            description="Visualize saved patches with optional YOLO bboxes.",
            parameters={
                "type": "object",
                "properties": {
                    "folder_name": {"type": "string", "default": "seg_patches"},
                    "patches_to_show": {"type": "integer", "default": 2},
                    "band_num": {"type": "integer", "default": 1},
                    "fig_size": {
                        "type": "array",
                        "items": {"type": "number"},
                        "default": [10, 20]
                    },
                    "dpi": {"type": "integer", "default": 96},
                    "show_bboxes": {"type": "boolean", "default": False}
                },
                "required": ["folder_name"]
            },
            requires_connection=False
        ),
        gp_visualize_handler
    )

    # 6) Prediction init
    registrar.tool(
        ToolSpec(
            slug="geopatch.pred_init",
            name="GeoPatch Prediction Init",
            description="Initialize PredictionPatch for inference tiling.",
            parameters={
                "type": "object",
                "properties": {
                    "image": {"description": "Path to .tif/.npy image or numpy array"},
                    "patch_size": {"type": "integer", "default": 128},
                    "stride": {"type": "integer", "default": 128},
                    "channel_first": {"type": "boolean", "default": True}
                },
                "required": ["image"]
            },
            requires_connection=False
        ),
        gp_pred_init_handler
    )

    # 7) Prediction save (GeoTIFF)
    registrar.tool(
        ToolSpec(
            slug="geopatch.pred_save_tif",
            name="GeoPatch Prediction Save (GeoTIFF)",
            description="Save prediction tiles as GeoTIFF files.",
            parameters={
                "type": "object",
                "properties": {
                    "folder_name": {"type": "string", "default": "pred_tif"}
                },
                "required": []
            },
            requires_connection=False
        ),
        gp_pred_save_tif_handler
    )

    # 8) Prediction save (NumPy)
    registrar.tool(
        ToolSpec(
            slug="geopatch.pred_save_npy",
            name="GeoPatch Prediction Save (NumPy)",
            description="Save prediction tiles as NumPy arrays.",
            parameters={
                "type": "object",
                "properties": {
                    "folder_name": {"type": "string", "default": "pred_npy"}
                },
                "required": []
            },
            requires_connection=False
        ),
        gp_pred_save_npy_handler
    )
