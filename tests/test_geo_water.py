from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from terrabox.toolkits.geo_water import (
    raster_profile_preflight_handler,
    sar_water_mask_handler,
    water_evidence_handler,
)


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

    def test_sar_water_mask_otsu_labels_low_backscatter(self):
        # Synthetic linear gamma0: 0.003 (about -25 dB) is water-like, 0.1 (-10 dB) land-like.
        sar = self.root / "sar.tif"
        out = self.root / "mask.tif"
        self._write_sar(sar, [[0.003, 0.003, 0.1], [0.1, -32768.0, 0.1]])
        result = sar_water_mask_handler({"input_path": str(sar), "output_path": str(out)}, None, None)
        self.assertTrue(result["success"])
        self.assertEqual(result["method"], "otsu")
        self.assertTrue(-25 < result["threshold_db"] <= -10)
        self.assertEqual(result["valid_pixels"], 5)
        self.assertEqual(result["water_pixels"], 2)
        with rasterio.open(out) as src:
            self.assertEqual(src.nodata, 255)
            self.assertEqual(src.read(1).tolist(), [[1, 1, 0], [0, 255, 0]])
            self.assertEqual(src.crs.to_string(), "EPSG:32634")

    def test_sar_water_mask_fixed_threshold_feeds_water_evidence(self):
        before_sar, after_sar = self.root / "before_sar.tif", self.root / "after_sar.tif"
        self._write_sar(before_sar, [[0.003, 0.1], [0.1, 0.1]])
        self._write_sar(after_sar, [[0.003, 0.003], [0.1, 0.003]])
        masks = []
        for name, path in (("before_mask.tif", before_sar), ("after_mask.tif", after_sar)):
            out = self.root / name
            result = sar_water_mask_handler(
                {"input_path": str(path), "output_path": str(out), "threshold_db": -18.0}, None, None
            )
            self.assertEqual(result["method"], "fixed")
            masks.append(str(out))
        evidence = water_evidence_handler({"before_path": masks[0], "after_path": masks[1]}, None, None)
        self.assertTrue(evidence["success"])
        self.assertEqual(evidence["before_water_pixels"], 1)
        self.assertEqual(evidence["after_water_pixels"], 3)
        self.assertAlmostEqual(evidence["new_water_area_m2"], 200.0)

    def test_sar_water_mask_blocks_when_no_valid_pixels(self):
        sar = self.root / "empty.tif"
        self._write_sar(sar, [[-32768.0, 0.0]])
        result = sar_water_mask_handler({"input_path": str(sar), "output_path": str(self.root / "m.tif")}, None, None)
        self.assertTrue(result["execution_blocked"])
        self.assertEqual(result["reason_code"], "no_valid_pixels")


if __name__ == "__main__":
    unittest.main()
