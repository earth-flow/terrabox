from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from terrabox.toolkits.geo_water import raster_profile_preflight_handler, water_evidence_handler


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


if __name__ == "__main__":
    unittest.main()
