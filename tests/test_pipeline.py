import os
from pathlib import Path
import struct
import tempfile
import unittest
import numpy as np
from PIL import Image

from app.pipeline.calibration import calibrate_elevation, fit_linear_scale_offset
from app.pipeline.estimator import DepthAnythingV2Estimator, MockDepthEstimator
from app.pipeline.geospatial import generate_colorized_preview, save_dsm_geotiff
from app.pipeline.mesh_builder import build_terrain_glb, generate_terrain_mesh


class TestElevationPipeline(unittest.TestCase):

    def setUp(self):
        self.test_img = Image.new("RGB", (128, 128), color=(100, 150, 200))
        self.estimator = MockDepthEstimator()

    def test_depth_estimation_shape_and_bounds(self):
        heightmap = self.estimator.estimate(self.test_img)
        self.assertEqual(heightmap.shape, (128, 128))
        self.assertEqual(heightmap.dtype, np.float32)
        self.assertGreaterEqual(float(heightmap.min()), 0.0)
        self.assertLessEqual(float(heightmap.max()), 1.0)

    def test_scale_calibration_non_georeferenced(self):
        rel_depth = np.linspace(0.0, 1.0, 100).reshape((10, 10)).astype(np.float32)
        res = calibrate_elevation(rel_depth, is_georeferenced=False)
        self.assertIsNone(res.rmse)
        self.assertIsNone(res.mae)
        self.assertAlmostEqual(res.elevation_min, 0.0, places=3)
        self.assertAlmostEqual(res.elevation_max, 100.0, places=3)
        self.assertIn("Relative", res.calibration_source)
        self.assertFalse(res.is_synthetic)

    def test_scale_calibration_georeferenced(self):
        rel_depth = np.linspace(0.1, 0.9, 100).reshape((10, 10)).astype(np.float32)
        res = calibrate_elevation(rel_depth, is_georeferenced=True)
        self.assertIsNotNone(res.rmse)
        self.assertIsNotNone(res.mae)
        self.assertIsNotNone(res.correlation)
        self.assertGreater(res.elevation_max, res.elevation_min)
        self.assertIsNotNone(res.calibration_source)

    def test_mesh_generation(self):
        elevation = np.zeros((32, 32), dtype=np.float32)
        verts, norms, uvs, indices = generate_terrain_mesh(elevation, target_res=16, adaptive_decimate=False)

        # 16x16 grid = 256 vertices
        self.assertEqual(len(verts), 256)
        self.assertEqual(len(norms), 256)
        self.assertEqual(len(uvs), 256)
        # (16 - 1) * (16 - 1) * 2 triangles = 450 triangles
        self.assertEqual(len(indices), 450)

    def test_adaptive_mesh_decimation(self):
        # Flat plane with small central peak
        elevation = np.zeros((32, 32), dtype=np.float32)
        elevation[14:18, 14:18] = 50.0

        # Regular triangulation
        _, _, _, regular_indices = generate_terrain_mesh(elevation, target_res=16, adaptive_decimate=False)
        # Adaptive decimation
        _, _, _, decimated_indices = generate_terrain_mesh(elevation, target_res=16, adaptive_decimate=True)

        self.assertEqual(len(regular_indices), 450)
        # Adaptive decimation should reduce flat cells, producing fewer triangles
        self.assertLess(len(decimated_indices), len(regular_indices))
        self.assertGreater(len(decimated_indices), 200)

    def test_srtm_tile_fetching_fallback(self):
        from app.pipeline.calibration import fetch_srtm_elevation_tile
        # Test bounds in Himalayas
        bounds = {"left": 77.10, "bottom": 32.20, "right": 77.20, "top": 32.30}
        tile = fetch_srtm_elevation_tile(bounds, "EPSG:4326", (16, 16))
        # When offline or uncached, gracefully returns None
        if tile is not None:
            self.assertEqual(tile.shape, (16, 16))

        # Test calibrate_elevation with geographic bounds
        rel_depth = np.linspace(0.1, 0.9, 100).reshape((10, 10)).astype(np.float32)
        res = calibrate_elevation(rel_depth, is_georeferenced=True, bounds=bounds)
        self.assertIsNotNone(res.rmse)
        self.assertIsNotNone(res.correlation)
        self.assertGreater(res.elevation_max, res.elevation_min)

    def test_glb_export(self):
        elevation = np.random.rand(32, 32).astype(np.float32)
        with tempfile.NamedTemporaryFile(suffix=".glb", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            out = build_terrain_glb(
                elevation_map=elevation,
                texture_image=self.test_img,
                output_path=tmp_path,
                grid_resolution=16
            )
            self.assertTrue(out.exists())
            self.assertGreater(out.stat().st_size, 1024)

            # Validate binary glTF magic header: b'glTF' and version 2
            with open(out, "rb") as f:
                magic, version, length = struct.unpack("<4sII", f.read(12))
                self.assertEqual(magic, b"glTF")
                self.assertEqual(version, 2)
                self.assertEqual(length, out.stat().st_size)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    def test_dsm_geotiff_and_preview_export(self):
        elevation = np.linspace(500, 1500, 64 * 64).reshape((64, 64)).astype(np.float32)
        with tempfile.TemporaryDirectory() as tmpdir:
            dsm_path = Path(tmpdir) / "test_dsm.tif"
            preview_path = Path(tmpdir) / "test_preview.png"

            save_dsm_geotiff(elevation, dsm_path)
            generate_colorized_preview(elevation, preview_path)

            self.assertTrue(dsm_path.exists())
            self.assertTrue(preview_path.exists())

    def test_gcp_calibration_and_csv_parsing(self):
        from app.pipeline.calibration import parse_gcp_csv
        csv_data = """pixel_x,pixel_y,elevation
10,10,500.0
50,50,1200.0
80,80,1800.0
"""
        gcps = parse_gcp_csv(csv_data)
        self.assertEqual(len(gcps), 3)
        self.assertEqual(gcps[0]["elevation"], 500.0)

        rel_depth = np.linspace(0.1, 0.9, 100 * 100).reshape((100, 100)).astype(np.float32)
        res = calibrate_elevation(rel_depth, is_georeferenced=False, gcps=gcps)
        self.assertIsNotNone(res.rmse)
        self.assertIsNotNone(res.mae)
        self.assertIsNotNone(res.correlation)
        self.assertGreater(res.elevation_max, res.elevation_min)
        self.assertGreater(res.correlation, 0.95)

    def test_real_estimator_fallback_reports_used_fallback(self):
        """When _load() fails (no weights/net/CUDA), estimate() must fall back to
        mock AND report it via used_fallback so callers can label honestly."""
        estimator = DepthAnythingV2Estimator(model_name="nonexistent/model-xyz")
        # Force the load to fail regardless of environment.
        estimator._load = lambda: None  # never initializes
        estimator._initialized = False
        estimator._model = None
        estimator._processor = None

        heightmap = estimator.estimate(self.test_img)

        self.assertEqual(heightmap.shape, self.test_img.size[::-1])
        self.assertTrue(estimator.used_fallback)
        self.assertFalse(estimator._initialized)

    def test_real_estimator_success_clears_fallback_flag(self):
        """A successful real inference must report used_fallback=False, even if a
        previous call on the same instance fell back (mid-session recovery)."""
        estimator = DepthAnythingV2Estimator()
        # Stub _load so the test never touches the network/HF cache.
        estimator._load = lambda: None

        # First: a fallback occurs (e.g. load failure mid-session)
        estimator._initialized = False
        estimator._model = None
        self.assertTrue(estimator.estimate(self.test_img).shape[0] > 0)
        self.assertTrue(estimator.used_fallback)

        # Then: model becomes available (e.g. weights finished downloading)
        estimator._initialized = True
        estimator._model = object()
        estimator._processor = object()
        estimator._estimate_real = lambda image: np.zeros(
            (image.size[1], image.size[0]), dtype=np.float32
        )
        result = estimator.estimate(self.test_img)
        self.assertFalse(estimator.used_fallback)
        self.assertEqual(result.shape, (self.test_img.size[1], self.test_img.size[0]))

    def test_force_mock_override_reports_fallback(self):
        """USE_MOCK_MODEL dev override must also yield used_fallback=True."""
        estimator = DepthAnythingV2Estimator()
        estimator.force_mock()
        heightmap = estimator.estimate(self.test_img)
        self.assertEqual(heightmap.shape, self.test_img.size[::-1])
        self.assertTrue(estimator.used_fallback)

    def test_runner_label_reflects_actual_outcome(self):
        """runner.run_pipeline_for_job must set job.model_name from the estimator's
        reported outcome, not an assumption made before inference."""
        import inspect
        from app.pipeline import runner as runner_module

        source = inspect.getsource(runner_module.run_pipeline_for_job)
        # Label derivation must happen AFTER estimate() has run
        self.assertGreater(
            source.index("model_label = "),
            source.index("estimator.estimate(rgb_img)"),
            "model_label must be derived after estimate() reports its outcome",
        )
        self.assertIn('model_label = "Mock Dev Mode"', source)
        self.assertIn('model_label = "Depth Anything V2 (PyTorch)"', source)
        self.assertIn("estimator.used_fallback", source)

    def test_compute_slope_profile(self):
        from app.pipeline.geospatial import compute_slope_profile
        # Flat plane
        flat = np.ones((50, 50), dtype=np.float32) * 100.0
        stats_flat = compute_slope_profile(flat, cell_size_m=30.0)
        self.assertAlmostEqual(stats_flat["mean_slope_deg"], 0.0, places=2)
        self.assertAlmostEqual(stats_flat["max_slope_deg"], 0.0, places=2)
        self.assertEqual(stats_flat["steep_terrain_pct"], 0.0)

        # 45-degree slope (rise = run: 30m rise per 30m cell)
        x = np.arange(50, dtype=np.float32) * 30.0
        ramp = np.tile(x, (50, 1))
        stats_ramp = compute_slope_profile(ramp, cell_size_m=30.0)
        self.assertGreater(stats_ramp["mean_slope_deg"], 40.0)
        self.assertGreater(stats_ramp["steep_terrain_pct"], 90.0)


if __name__ == "__main__":
    unittest.main()

