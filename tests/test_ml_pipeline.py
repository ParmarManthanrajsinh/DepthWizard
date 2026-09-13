import tempfile
import unittest
from pathlib import Path
import numpy as np
from PIL import Image

try:
    import torch
except ImportError:
    torch = None

from ml.dataset import SatelliteElevationDataset
from ml.evaluate import compute_mae, compute_pearson_correlation, compute_rmse
from ml.inference import DepthAnythingV2Baseline
from ml.preprocessing import (
    align_dem_to_image,
    create_dem_valid_mask,
    normalize_image,
)


class TestMLPipeline(unittest.TestCase):
    """
    Unit test suite for DepthWizard ML Foundation (SIH26175):
    - Dataset pairing and orphan file handling
    - Tensor conversions, dtypes, and shapes
    - NoData, NaN, and Inf DEM validity masking
    - Metric calculation (MAE, RMSE, Pearson r)
    - Depth Anything V2 baseline inference interface
    """

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root_path = Path(self.tmpdir.name)
        self.images_dir = self.root_path / "images"
        self.dem_dir = self.root_path / "dem"
        self.images_dir.mkdir(parents=True)
        self.dem_dir.mkdir(parents=True)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_dataset_pairing_and_orphans(self):
        # Create 2 paired scenes
        img1 = Image.new("RGB", (32, 32), color=(50, 100, 150))
        img1.save(self.images_dir / "scene_001.png")
        dem1 = Image.new("F", (32, 32), color=500.0)
        dem1.save(self.dem_dir / "scene_001.tif")

        img2 = Image.new("RGB", (32, 32), color=(60, 110, 160))
        img2.save(self.images_dir / "scene_002.png")
        dem2 = Image.new("F", (32, 32), color=600.0)
        dem2.save(self.dem_dir / "scene_002.tif")

        # Create orphan files
        img_orphan = Image.new("RGB", (32, 32), color=(0, 0, 0))
        img_orphan.save(self.images_dir / "orphan_optical.png")
        dem_orphan = Image.new("F", (32, 32), color=100.0)
        dem_orphan.save(self.dem_dir / "orphan_elevation.tif")

        dataset = SatelliteElevationDataset(self.root_path)

        # Only matched pairs should be included
        self.assertEqual(len(dataset), 2)
        stems = [p[0] for p in dataset.pairs]
        self.assertIn("scene_001", stems)
        self.assertIn("scene_002", stems)
        self.assertNotIn("orphan_optical", stems)
        self.assertNotIn("orphan_elevation", stems)

        # Unmatched files tracked
        self.assertEqual(len(dataset._unmatched_images), 1)
        self.assertEqual(len(dataset._unmatched_dems), 1)

    def test_tensor_shapes_and_dtypes(self):
        if torch is None:
            self.skipTest("PyTorch is not installed in this environment.")

        # Create paired test sample
        img = Image.new("RGB", (40, 30), color=(120, 140, 160))
        img.save(self.images_dir / "test_geo.png")
        dem = Image.new("F", (40, 30), color=850.0)
        dem.save(self.dem_dir / "test_geo.tif")

        dataset = SatelliteElevationDataset(self.root_path)
        item = dataset[0]

        self.assertEqual(item["stem"], "test_geo")
        # Image shape should be (3, H, W) = (3, 30, 40)
        self.assertEqual(item["image"].shape, (3, 30, 40))
        self.assertEqual(item["image"].dtype, torch.float32)

        # DEM shape should be (1, H, W) = (1, 30, 40)
        self.assertEqual(item["dem"].shape, (1, 30, 40))
        self.assertEqual(item["dem"].dtype, torch.float32)

        # Valid mask shape should be (1, H, W) = (1, 30, 40)
        self.assertEqual(item["valid_mask"].shape, (1, 30, 40))
        self.assertEqual(item["valid_mask"].dtype, torch.bool)

    def test_dem_valid_mask_and_nodata_filtering(self):
        # Construct DEM array with realistic mix of valid and invalid values
        dem = np.array([
            [500.0, 1200.0, -9999.0],    # -9999 is explicit NoData
            [np.nan, 2500.0, np.inf],     # NaN and Inf are invalid
            [-1000.0, 4500.0, 15000.0],   # -1000 and 15000 exceed terrestrial bounds
        ], dtype=np.float32)

        mask = create_dem_valid_mask(
            dem,
            nodata_value=-9999.0,
            min_valid=-500.0,
            max_valid=9000.0,
        )

        expected_mask = np.array([
            [True, True, False],
            [False, True, False],
            [False, True, False],
        ], dtype=bool)

        np.testing.assert_array_equal(mask, expected_mask)

    def test_mae_calculation(self):
        pred = np.array([10.0, 20.0, 30.0, 999.0], dtype=np.float32)
        target = np.array([12.0, 18.0, 35.0, 50.0], dtype=np.float32)
        mask = np.array([True, True, True, False], dtype=bool)

        # Residuals on valid pixels: |10-12|=2, |20-18|=2, |30-35|=5 -> mean = 3.0
        mae = compute_mae(pred, target, mask)
        self.assertAlmostEqual(mae, 3.0, places=5)

        # Test NaN auto-filtering
        pred_with_nan = np.array([10.0, 20.0, np.nan], dtype=np.float32)
        target_clean = np.array([12.0, 18.0, 100.0], dtype=np.float32)
        mae_nan = compute_mae(pred_with_nan, target_clean)
        self.assertAlmostEqual(mae_nan, 2.0, places=5)

    def test_rmse_calculation(self):
        pred = np.array([10.0, 20.0, 999.0], dtype=np.float32)
        target = np.array([13.0, 16.0, 0.0], dtype=np.float32)
        mask = np.array([True, True, False], dtype=bool)

        # Squared errors on valid pixels: (10-13)^2 = 9, (20-16)^2 = 16 -> mean = 12.5 -> sqrt = 3.5355...
        rmse = compute_rmse(pred, target, mask)
        self.assertAlmostEqual(rmse, float(np.sqrt(12.5)), places=5)

    def test_pearson_correlation(self):
        pred = np.array([1.0, 2.0, 3.0, 4.0, 999.0], dtype=np.float32)
        target = np.array([10.0, 20.0, 30.0, 40.0, 0.0], dtype=np.float32)
        mask = np.array([True, True, True, True, False], dtype=bool)

        corr = compute_pearson_correlation(pred, target, mask)
        self.assertAlmostEqual(corr, 1.0, places=5)

        # Negative correlation
        pred_inv = np.array([4.0, 3.0, 2.0, 1.0], dtype=np.float32)
        target_asc = np.array([10.0, 20.0, 30.0, 40.0], dtype=np.float32)
        corr_inv = compute_pearson_correlation(pred_inv, target_asc)
        self.assertAlmostEqual(corr_inv, -1.0, places=5)

    def test_inference_baseline_interface(self):
        # Use development mock mode to verify contract without downloading heavy model weights
        baseline = DepthAnythingV2Baseline(force_mock=True)

        test_img = Image.new("RGB", (64, 64), color=(100, 150, 200))
        rel_depth = baseline.predict_relative_depth(test_img)

        # Verification of relative depth contract
        self.assertEqual(rel_depth.shape, (64, 64))
        self.assertEqual(rel_depth.dtype, np.float32)
        self.assertGreaterEqual(float(rel_depth.min()), 0.0)
        self.assertLessEqual(float(rel_depth.max()), 1.0)

        # Verification of metric calibration step
        simulated_gt = 500.0 + 1000.0 * rel_depth
        calibrated_elev, stats = baseline.predict_metric_elevation(rel_depth, simulated_gt)

        self.assertEqual(calibrated_elev.shape, (64, 64))
        self.assertAlmostEqual(stats["scale"], 1000.0, places=1)
        self.assertAlmostEqual(stats["offset_meters"], 500.0, places=1)
        self.assertGreater(stats["correlation"], 0.99)


if __name__ == "__main__":
    unittest.main()
