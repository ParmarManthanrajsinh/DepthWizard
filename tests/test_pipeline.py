import os
from pathlib import Path
import struct
import tempfile
import unittest
import numpy as np
from PIL import Image

from app.pipeline.calibration import calibrate_elevation, fit_linear_scale_offset
from app.pipeline.estimator import MockDepthEstimator
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

    def test_scale_calibration_georeferenced(self):
        rel_depth = np.linspace(0.1, 0.9, 100).reshape((10, 10)).astype(np.float32)
        res = calibrate_elevation(rel_depth, is_georeferenced=True)
        self.assertIsNotNone(res.rmse)
        self.assertIsNotNone(res.mae)
        self.assertIsNotNone(res.correlation)
        self.assertGreater(res.elevation_max, res.elevation_min)

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


if __name__ == "__main__":
    unittest.main()
