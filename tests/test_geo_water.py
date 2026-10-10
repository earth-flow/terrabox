from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from terrabox.toolkits.geo_water import (
    compare_with_reference_handler,
    raster_profile_preflight_handler,
    water_by_class_handler,
    water_evidence_handler,
    water_extent_handler,
)
from terrabox.toolkits.georaster import threshold_segmentation_handler


class GeoWaterTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.before = self.root / "before.tif"
        self.after = self.root / "after.tif"
        self._write(self.before, [[0, 1], [0, 0]])
        self._write(self.after, [[1, 1], [0, 1]])

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write(self, path, values, *, crs="EPSG:32611", transform=None, nodata=255):
        data = np.asarray(values, dtype=np.uint8)
        profile = {
            "driver": "GTiff",
            "height": data.shape[0],
            "width": data.shape[1],
            "count": 1,
            "dtype": "uint8",
            "crs": crs,
            "transform": transform or from_origin(500000, 4100000, 10, 10),
            "nodata": nodata,
        }
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(data, 1)

    def _args(self):
        return {"before_path": str(self.before), "after_path": str(self.after)}

    def test_preflight_accepts_matching_projected_grids(self):
        result = raster_profile_preflight_handler(self._args(), None, None)
        self.assertTrue(result["success"])
        self.assertFalse(result["execution_blocked"])
        self.assertEqual(result["reason_code"], None)
        self.assertEqual(result["common_valid_pixels"], 4)
        self.assertTrue(result["grid_id"].startswith("grid:"))

    def test_preflight_blocks_declared_grid_mismatch(self):
        result = raster_profile_preflight_handler(
            {**self._args(), "before_grid_id": "grid-a", "after_grid_id": "grid-b"}, None, None
        )
        self.assertEqual(result["reason_code"], "grid_mismatch")
        self.assertTrue(result["execution_blocked"])

    def test_preflight_blocks_shape_crs_and_transform_mismatch(self):
        different = self.root / "different.tif"
        self._write(different, [[0, 1, 0], [1, 0, 1]])
        result = raster_profile_preflight_handler({**self._args(), "after_path": str(different)}, None, None)
        self.assertEqual(result["reason_code"], "shape_mismatch")

        self._write(different, [[0, 1], [1, 0]], crs="EPSG:32610")
        result = raster_profile_preflight_handler({**self._args(), "after_path": str(different)}, None, None)
        self.assertEqual(result["reason_code"], "crs_mismatch")

        self._write(different, [[0, 1], [1, 0]], transform=from_origin(500010, 4100000, 10, 10))
        result = raster_profile_preflight_handler({**self._args(), "after_path": str(different)}, None, None)
        self.assertEqual(result["reason_code"], "transform_mismatch")

    def test_water_evidence_uses_common_support_and_projected_area(self):
        result = water_evidence_handler(self._args(), None, None)
        self.assertTrue(result["success"])
        self.assertTrue(result["change_answerable"])
        self.assertEqual(result["semantic_class"], "water_not_flood")
        self.assertEqual(result["valid_pixels"], 4)
        self.assertEqual(result["pixel_area_m2"], 100)
        self.assertEqual(result["before_water_area_m2"], 100)
        self.assertEqual(result["after_water_area_m2"], 300)
        self.assertEqual(result["new_water_area_m2"], 200)
        self.assertEqual(result["receded_water_area_m2"], 0)

    def test_water_evidence_rechecks_grid_and_rejects_invalid_labels(self):
        mismatch = water_evidence_handler(
            {**self._args(), "before_grid_id": "one", "after_grid_id": "two"}, None, None
        )
        self.assertTrue(mismatch["execution_blocked"])
        self.assertEqual(mismatch["reason_code"], "grid_mismatch")

        self._write(self.after, [[0, 2], [0, 1]])
        invalid = water_evidence_handler(self._args(), None, None)
        self.assertEqual(invalid["reason_code"], "invalid_water_labels")
        self.assertTrue(invalid["execution_blocked"])

    def test_water_evidence_rejects_geographic_area_estimates(self):
        self._write(self.before, [[0, 1], [0, 0]], crs="EPSG:4326")
        self._write(self.after, [[1, 1], [0, 1]], crs="EPSG:4326")
        result = water_evidence_handler(self._args(), None, None)
        self.assertEqual(result["reason_code"], "unsupported_area_crs")
        self.assertTrue(result["execution_blocked"])


    def test_water_evidence_rejects_web_mercator_area(self):
        mercator = from_origin(2450000, 4790000, 10, 10)
        self._write(self.before, [[0, 1], [0, 0]], crs="EPSG:3857", transform=mercator)
        self._write(self.after, [[1, 1], [0, 1]], crs="EPSG:3857", transform=mercator)
        result = water_evidence_handler(self._args(), None, None)
        self.assertEqual(result["reason_code"], "area_distorting_projection")
        self.assertTrue(result["execution_blocked"])
        self.assertFalse(result["change_answerable"])

    def test_water_extent_counts_valid_pixels_only(self):
        self._write(self.after, [[1, 255], [0, 1]])
        result = water_extent_handler({"label_path": str(self.after)}, None, None)
        self.assertTrue(result["success"])
        self.assertEqual(result["valid_pixels"], 3)
        self.assertEqual(result["excluded_pixels"], 1)
        self.assertEqual(result["water_pixels"], 2)
        self.assertEqual(result["pixel_area_m2"], 100)
        self.assertEqual(result["water_area_m2"], 200)
        self.assertEqual(result["valid_area_m2"], 300)
        self.assertAlmostEqual(result["water_fraction"], 2 / 3)
        self.assertEqual(result["projection_method"], "Transverse Mercator")

    def test_water_extent_blocks_invalid_labels_and_bad_area_grids(self):
        self._write(self.after, [[0, 2], [0, 1]])
        result = water_extent_handler({"label_path": str(self.after)}, None, None)
        self.assertEqual(result["reason_code"], "invalid_water_labels")
        self._write(self.after, [[0, 1], [0, 1]], crs="EPSG:4326", transform=from_origin(22.0, 39.5, 0.0001, 0.0001))
        result = water_extent_handler({"label_path": str(self.after)}, None, None)
        self.assertEqual(result["reason_code"], "unsupported_area_crs")
        self._write(self.after, [[0, 1], [0, 1]], crs="EPSG:3857", transform=from_origin(2450000, 4790000, 10, 10))
        result = water_extent_handler({"label_path": str(self.after)}, None, None)
        self.assertEqual(result["reason_code"], "area_distorting_projection")
        self.assertTrue(result["execution_blocked"])
        self._write(self.after, [[255, 255], [255, 255]])
        result = water_extent_handler({"label_path": str(self.after)}, None, None)
        self.assertEqual(result["reason_code"], "no_valid_pixels")

    def _write_sar(self, path, values, nodata=-32768.0):
        data = np.asarray(values, dtype=np.float32)
        profile = {
            "driver": "GTiff",
            "height": data.shape[0],
            "width": data.shape[1],
            "count": 1,
            "dtype": "float32",
            "crs": "EPSG:32634",
            "transform": from_origin(500000, 4400000, 10, 10),
            "nodata": nodata,
        }
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(data, 1)

    # Scenario preset used by the Terraflow water runner for linear SAR backscatter.
    SAR_WATER = {
        "direction": "below",
        "input_transform": "db",
        "foreground_value": 1,
        "background_value": 0,
        "nodata_value": 255,
    }

    def test_threshold_defaults_are_unchanged(self):
        raster = self.root / "frp.tif"
        out = self.root / "frp_mask.tif"
        self._write_sar(raster, [[0.0, 2.0], [5.0, 1.0]])
        result = threshold_segmentation_handler(
            {"input_path": str(raster), "threshold": 1.0, "output_path": str(out)}, None, None
        )
        self.assertEqual(result["method"], "fixed")
        with rasterio.open(out) as src:
            self.assertEqual(src.read(1).tolist(), [[0, 255], [255, 0]])
            self.assertEqual(src.nodata, 0)

    def test_sar_preset_otsu_labels_low_backscatter(self):
        # Synthetic linear gamma0: 0.003 (about -25 dB) is water-like, 0.1 (-10 dB) land-like.
        sar = self.root / "sar.tif"
        out = self.root / "mask.tif"
        self._write_sar(sar, [[0.003, 0.003, 0.1], [0.1, -32768.0, 0.1]])
        result = threshold_segmentation_handler(
            {"input_path": str(sar), "output_path": str(out), "method": "otsu", **self.SAR_WATER}, None, None
        )
        self.assertEqual(result["method"], "otsu")
        self.assertTrue(-25 < result["threshold"] <= -10)
        self.assertEqual(result["valid_pixels"], 5)
        self.assertEqual(result["foreground_pixels"], 2)
        with rasterio.open(out) as src:
            self.assertEqual(src.nodata, 255)
            self.assertEqual(src.read(1).tolist(), [[1, 1, 0], [0, 255, 0]])
            self.assertEqual(src.crs.to_string(), "EPSG:32634")

    def test_sar_preset_fixed_threshold_feeds_water_evidence(self):
        before_sar, after_sar = self.root / "before_sar.tif", self.root / "after_sar.tif"
        self._write_sar(before_sar, [[0.003, 0.1], [0.1, 0.1]])
        self._write_sar(after_sar, [[0.003, 0.003], [0.1, 0.003]])
        masks = []
        for name, path in (("before_mask.tif", before_sar), ("after_mask.tif", after_sar)):
            out = self.root / name
            result = threshold_segmentation_handler(
                {"input_path": str(path), "output_path": str(out), "threshold": -18.0, **self.SAR_WATER}, None, None
            )
            self.assertEqual(result["method"], "fixed")
            masks.append(str(out))
        evidence = water_evidence_handler({"before_path": masks[0], "after_path": masks[1]}, None, None)
        self.assertTrue(evidence["success"])
        self.assertEqual(evidence["before_water_pixels"], 1)
        self.assertEqual(evidence["after_water_pixels"], 3)
        self.assertAlmostEqual(evidence["new_water_area_m2"], 200.0)

    def test_threshold_blocks_when_no_valid_pixels(self):
        sar = self.root / "empty.tif"
        self._write_sar(sar, [[-32768.0, 0.0]])
        result = threshold_segmentation_handler(
            {"input_path": str(sar), "output_path": str(self.root / "m.tif"), "method": "otsu", **self.SAR_WATER},
            None,
            None,
        )
        self.assertTrue(result["execution_blocked"])
        self.assertEqual(result["reason_code"], "no_valid_pixels")

    def test_threshold_rejects_ambiguous_label_values(self):
        sar = self.root / "x.tif"
        self._write_sar(sar, [[0.1, 0.2]])
        with self.assertRaises(ValueError):
            threshold_segmentation_handler(
                {"input_path": str(sar), "output_path": str(self.root / "m.tif"), "threshold": 0.15,
                 "foreground_value": 1, "background_value": 0, "nodata_value": 1},
                None,
                None,
            )


class WaterByClassAndReferenceTests(unittest.TestCase):
    """Synthetic 3x3 rasters on a 10 m UTM grid (100 m2 per pixel)."""

    CLASSES = [
        {"value": 0, "name": "no_data", "nodata": True},
        {"value": 40, "name": "cropland", "title": "耕地"},
        {"value": 50, "name": "built_up", "title": "建设用地"},
    ]

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write(self, name, values, *, crs="EPSG:32634", nodata=255, transform=None):
        path = self.root / name
        data = np.asarray(values, dtype=np.uint8)
        with rasterio.open(
            path, "w", driver="GTiff", height=data.shape[0], width=data.shape[1], count=1, dtype="uint8",
            crs=crs, transform=transform or from_origin(586300, 4382310, 10, 10), nodata=nodata,
        ) as dst:
            dst.write(data, 1)
        return str(path)

    def _class_args(self, classes_values, **extra):
        return {
            "before_path": self._write("before.tif", [[0, 0, 1], [0, 0, 0], [0, 0, 0]]),
            "after_path": self._write("after.tif", [[1, 1, 1], [1, 0, 0], [0, 0, 255]]),
            "class_path": self._write("classes.tif", classes_values, nodata=None),
            "classes": self.CLASSES,
            **extra,
        }

    def test_new_water_by_class(self):
        args = self._class_args([[40, 40, 40], [50, 50, 50], [40, 0, 40]], output_path=str(self.root / "o.tif"))
        result = water_by_class_handler(args, None, None)
        self.assertTrue(result["class_answerable"])
        rows = {row["name"]: row for row in result["classes"]}
        # valid: 9 pixels minus after-nodata (2,2) minus class nodata (2,1) = 7
        self.assertEqual(result["valid_pixels"], 7)
        self.assertEqual(rows["cropland"]["class_area_m2"], 400)
        self.assertEqual(rows["cropland"]["new_water_area_m2"], 200)
        self.assertEqual(rows["built_up"]["new_water_area_m2"], 100)
        self.assertAlmostEqual(rows["cropland"]["share_of_new_water"], 2 / 3)
        with rasterio.open(args["output_path"]) as src:
            self.assertEqual(src.read(1).tolist(), [[40, 40, 0], [50, 0, 0], [0, 255, 255]])

    def test_undeclared_class_value_blocks(self):
        result = water_by_class_handler(self._class_args([[40, 37, 40], [50, 50, 50], [40, 0, 40]]), None, None)
        self.assertTrue(result["execution_blocked"])
        self.assertEqual(result["reason_code"], "undeclared_class_values")
        self.assertEqual(result["undeclared_values"], [37])

    def test_class_grid_mismatch_blocks(self):
        args = self._class_args([[40, 40, 40], [50, 50, 50], [40, 0, 40]])
        args["class_path"] = self._write("shifted.tif", [[40] * 3] * 3, nodata=None,
                                         transform=from_origin(586310, 4382310, 10, 10))
        result = water_by_class_handler(args, None, None)
        self.assertEqual(result["reason_code"], "transform_mismatch")

    def test_geographic_class_grid_blocks_area(self):
        transform = from_origin(22.0, 39.5, 0.0001, 0.0001)
        args = {
            "after_path": self._write("a.tif", [[1, 0]], crs="EPSG:4326", transform=transform),
            "class_path": self._write("c.tif", [[40, 40]], crs="EPSG:4326", transform=transform, nodata=None),
            "classes": self.CLASSES,
        }
        self.assertEqual(water_by_class_handler(args, None, None)["reason_code"], "unsupported_area_crs")

    def test_compare_with_reference(self):
        predicted = self._write("p.tif", [[1, 1, 0], [0, 1, 0], [0, 0, 255]])
        reference = self._write("r.tif", [[1, 0, 1], [0, 1, 0], [0, 0, 0]])
        result = compare_with_reference_handler(
            {"predicted_path": predicted, "reference_path": reference, "output_path": str(self.root / "c.tif")},
            None, None,
        )
        self.assertEqual((result["true_positive_pixels"], result["false_positive_pixels"],
                          result["false_negative_pixels"], result["true_negative_pixels"]), (2, 1, 1, 4))
        self.assertAlmostEqual(result["precision"], 2 / 3)
        self.assertAlmostEqual(result["recall"], 2 / 3)
        self.assertAlmostEqual(result["iou"], 0.5)
        self.assertEqual(result["agreement_area_m2"], 200)
        with rasterio.open(result["output_path"]) as src:
            self.assertEqual(src.read(1).tolist(), [[1, 2, 3], [0, 1, 0], [0, 0, 255]])

    def test_compare_rejects_non_binary_reference(self):
        predicted = self._write("p.tif", [[1, 0]])
        reference = self._write("r.tif", [[2, 0]])
        result = compare_with_reference_handler({"predicted_path": predicted, "reference_path": reference}, None, None)
        self.assertEqual(result["reason_code"], "invalid_water_labels")

    def test_preflight_treats_nan_nodata_as_equal(self):
        paths = []
        for name in ("a.tif", "b.tif"):
            path = self.root / name
            with rasterio.open(path, "w", driver="GTiff", height=1, width=2, count=1, dtype="float32",
                               crs="EPSG:32634", transform=from_origin(586300, 4382310, 10, 10),
                               nodata=float("nan")) as dst:
                dst.write(np.array([[0.1, np.nan]], dtype="float32"), 1)
            paths.append(str(path))
        result = raster_profile_preflight_handler({"before_path": paths[0], "after_path": paths[1]}, None, None)
        self.assertFalse(result["execution_blocked"])
        self.assertIsNone(result["reason_code"])

    def test_compare_blocks_web_mercator(self):
        transform = from_origin(2450000, 4790000, 10, 10)
        predicted = self._write("p.tif", [[1, 0]], crs="EPSG:3857", transform=transform)
        reference = self._write("r.tif", [[1, 0]], crs="EPSG:3857", transform=transform)
        result = compare_with_reference_handler({"predicted_path": predicted, "reference_path": reference}, None, None)
        self.assertEqual(result["reason_code"], "area_distorting_projection")


if __name__ == "__main__":
    unittest.main()
