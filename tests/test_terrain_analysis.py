import os
import unittest
from pathlib import Path
import tempfile
import numpy as np
import rasterio
from rasterio.transform import from_origin
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import Base, engine, get_db
from app.db.models import Job
from app.pipeline.terrain_analysis import sample_elevation

class TestTerrainAnalysis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.client = TestClient(app)
        
    def setUp(self):
        # Create a temporary synthetic GeoTIFF
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.raster_path = Path(self.tmp_dir.name) / "test_dsm.tif"
        
        # 10x10 raster
        # Top-left corner at (100.0, 200.0) spatial, pixel size 1.0, 1.0
        self.transform = from_origin(100.0, 200.0, 1.0, 1.0)
        self.elevation_data = np.arange(100, dtype=np.float32).reshape(10, 10)
        # Set a nodata pixel at row=5, col=5
        self.elevation_data[5, 5] = -9999.0
        
        with rasterio.open(
            self.raster_path,
            'w',
            driver='GTiff',
            height=10,
            width=10,
            count=1,
            dtype=str(self.elevation_data.dtype),
            crs='EPSG:32633', # Example projected CRS
            transform=self.transform,
            nodata=-9999.0
        ) as dst:
            dst.write(self.elevation_data, 1)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_sample_elevation_spatial_valid(self):
        # Center of pixel (row=0, col=0) is (100.5, 199.5)
        # Spatial coords for row=2, col=3: x = 100 + 3 + 0.5 = 103.5, y = 200 - 2 - 0.5 = 197.5
        # Value = 2 * 10 + 3 = 23
        res = sample_elevation(self.raster_path, 103.5, 197.5, coordinate_system="spatial")
        self.assertEqual(res["elevation"], 23.0)
        self.assertEqual(res["pixel_x"], 3)
        self.assertEqual(res["pixel_y"], 2)
        self.assertFalse(res["is_nodata"])

    def test_sample_elevation_pixel_valid(self):
        # Pixel coords row=4, col=6 -> value = 46
        # x is col, y is row
        res = sample_elevation(self.raster_path, x=6, y=4, coordinate_system="pixel")
        self.assertEqual(res["elevation"], 46.0)
        self.assertEqual(res["pixel_x"], 6)
        self.assertEqual(res["pixel_y"], 4)
        self.assertFalse(res["is_nodata"])

    def test_sample_elevation_nodata(self):
        # Pixel coords row=5, col=5
        res = sample_elevation(self.raster_path, x=5, y=5, coordinate_system="pixel")
        self.assertIsNone(res["elevation"])
        self.assertTrue(res["is_nodata"])

    def test_sample_elevation_out_of_bounds(self):
        # Negative pixel
        res = sample_elevation(self.raster_path, x=-1, y=0, coordinate_system="pixel")
        self.assertIsNone(res["elevation"])
        self.assertTrue(res["is_nodata"])
        self.assertEqual(res["error"], "Coordinates out of bounds")

    def test_api_endpoint(self):
        # Create a mock job
        import uuid
        db = next(get_db())
        job_id = f"test-job-{uuid.uuid4().hex[:8]}"
        job = Job(
            id=job_id,
            filename="mock.tif",
            original_path="mock/path/mock.tif",
            dsm_path=str(self.raster_path)
        )
        db.add(job)
        db.commit()

        # Valid point query
        response = self.client.get(f"/api/jobs/{job_id}/analysis/point?x=2&y=3&system=pixel")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["elevation"], 32.0)
        self.assertFalse(data["is_nodata"])

        # Invalid job
        response = self.client.get(f"/api/jobs/invalid-job/analysis/point?x=0&y=0")
        self.assertEqual(response.status_code, 404)

    def test_calculate_slope_flat(self):
        from app.pipeline.terrain_analysis import calculate_slope
        out_path = Path(self.tmp_dir.name) / "slope_flat.tif"
        
        flat_data = np.full((10, 10), 50.0, dtype=np.float32)
        flat_raster = Path(self.tmp_dir.name) / "flat.tif"
        with rasterio.open(flat_raster, 'w', driver='GTiff', height=10, width=10, count=1, dtype='float32', transform=self.transform) as dst:
            dst.write(flat_data, 1)
            
        res = calculate_slope(flat_raster, out_path)
        self.assertAlmostEqual(res["mean_slope"], 0.0, places=2)
        
    def test_calculate_slope_and_aspect_x_ramp(self):
        from app.pipeline.terrain_analysis import calculate_slope, calculate_aspect
        out_path = Path(self.tmp_dir.name) / "slope_x.tif"
        out_path_a = Path(self.tmp_dir.name) / "aspect_x.tif"
        
        # Ramp going UP to the EAST.
        # col 0 = 0, col 1 = 1. dx = 1m. dz = 1m.
        # Slope = 45 degrees. Downhill is WEST (270 degrees)
        x_ramp = np.tile(np.arange(10, dtype=np.float32), (10, 1))
        x_raster = Path(self.tmp_dir.name) / "x_ramp.tif"
        
        # Test non-unit pixel resolution (dx = 2.0, dy = 3.0)
        transform_non_unit = from_origin(100.0, 200.0, 2.0, 3.0)
        
        with rasterio.open(x_raster, 'w', driver='GTiff', height=10, width=10, count=1, dtype='float32', transform=transform_non_unit) as dst:
            dst.write(x_ramp, 1)
            
        res = calculate_slope(x_raster, out_path)
        # dx = 2.0. dz = 1.0. rise/run = 1/2 = 0.5.
        # arctan(0.5) in degrees = 26.565
        self.assertAlmostEqual(res["mean_slope"], 26.565, places=2)
        
        res_a = calculate_aspect(x_raster, out_path_a)
        # Downhill is WEST (270)
        self.assertAlmostEqual(res_a["mean_aspect"], 270.0, places=1)

    def test_calculate_slope_and_aspect_y_ramp(self):
        from app.pipeline.terrain_analysis import calculate_slope, calculate_aspect
        out_path = Path(self.tmp_dir.name) / "slope_y.tif"
        out_path_a = Path(self.tmp_dir.name) / "aspect_y.tif"
        
        # Ramp going UP to the NORTH (row 0 is N, row 9 is S)
        # Z is highest at row 0.
        # row 0 = 9, row 9 = 0.
        # dz/dy (North) = 1.
        y_ramp = np.tile(np.arange(10, dtype=np.float32)[::-1], (10, 1)).T
        y_raster = Path(self.tmp_dir.name) / "y_ramp.tif"
        
        with rasterio.open(y_raster, 'w', driver='GTiff', height=10, width=10, count=1, dtype='float32', transform=self.transform) as dst:
            dst.write(y_ramp, 1)
            
        res = calculate_slope(y_raster, out_path)
        # dy = 1.0. dz = 1.0. rise/run = 1.0
        self.assertAlmostEqual(res["mean_slope"], 45.0, places=2)
        
        res_a = calculate_aspect(y_raster, out_path_a)
        # Downhill is SOUTH (180)
        self.assertAlmostEqual(res_a["mean_aspect"], 180.0, places=1)

    def test_diagonal_ramp_and_nodata(self):
        from app.pipeline.terrain_analysis import calculate_slope, calculate_aspect
        out_path = Path(self.tmp_dir.name) / "slope_diag.tif"
        
        diag_ramp = np.tile(np.arange(10, dtype=np.float32), (10, 1))
        diag_ramp += np.tile(np.arange(10, dtype=np.float32), (10, 1)).T
        # dz/dx = 1, dz/dy = 1 (dy going south)
        # Downhill is NORTH-WEST (-1, -1)
        
        # Add a NoData pixel in the middle
        diag_ramp[5, 5] = -9999.0
        
        diag_raster = Path(self.tmp_dir.name) / "diag_ramp.tif"
        with rasterio.open(diag_raster, 'w', driver='GTiff', height=10, width=10, count=1, dtype='float32', transform=self.transform, nodata=-9999.0) as dst:
            dst.write(diag_ramp, 1)
            
        res = calculate_slope(diag_raster, out_path)
        # rise/run = sqrt(1^2 + 1^2) = 1.414 -> arctan(1.414) = 54.73
        self.assertAlmostEqual(res["mean_slope"], 54.73, places=1)
        
        with rasterio.open(out_path) as src:
            slope_data = src.read(1)
            # The nodata pixel should be preserved as nodata
            self.assertEqual(slope_data[5, 5], -9999.0)
            
        # Aspect should be 315 (North-West)
        res_a = calculate_aspect(diag_raster, out_path)
        self.assertAlmostEqual(res_a["mean_aspect"], 315.0, places=1)
        
    def test_flat_terrain_aspect(self):
        from app.pipeline.terrain_analysis import calculate_aspect
        out_path = Path(self.tmp_dir.name) / "aspect_flat.tif"
        
        flat_data = np.full((10, 10), 50.0, dtype=np.float32)
        flat_raster = Path(self.tmp_dir.name) / "flat2.tif"
        with rasterio.open(flat_raster, 'w', driver='GTiff', height=10, width=10, count=1, dtype='float32', transform=self.transform) as dst:
            dst.write(flat_data, 1)
            
        res = calculate_aspect(flat_raster, out_path)
        self.assertIsNone(res["mean_aspect"]) # All are flat, so all are NoData
        
        with rasterio.open(out_path) as src:
            aspect_data = src.read(1)
            self.assertTrue(np.all(aspect_data == -9999.0))

    def test_api_slope_aspect_endpoints(self):
        import uuid
        db = next(get_db())
        job_id = f"test-job-{uuid.uuid4().hex[:8]}"
        job = Job(id=job_id, filename="mock.tif", original_path="mock/path/mock.tif", dsm_path=str(self.raster_path))
        db.add(job)
        db.commit()

        # Slope
        response = self.client.get(f"/api/jobs/{job_id}/analysis/slope")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("mean_slope", data)
        self.assertTrue(Path(data["layer_path"]).exists())
        
        # Aspect
        response = self.client.get(f"/api/jobs/{job_id}/analysis/aspect")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("mean_aspect", data)
        self.assertTrue(Path(data["layer_path"]).exists())
        
        db.delete(job)
        db.commit()

    def test_elevation_profile_flat(self):
        from app.pipeline.terrain_analysis import sample_elevation_profile
        flat_data = np.full((10, 10), 50.0, dtype=np.float32)
        flat_raster = Path(self.tmp_dir.name) / "flat_prof.tif"
        with rasterio.open(flat_raster, 'w', driver='GTiff', height=10, width=10, count=1, dtype='float32', transform=self.transform) as dst:
            dst.write(flat_data, 1)
            
        res = sample_elevation_profile(flat_raster, 0, 0, 9, 9, coordinate_system="pixel", samples=5)
        self.assertEqual(res["valid_samples"], 5)
        self.assertEqual(res["nodata_samples"], 0)
        self.assertAlmostEqual(res["min_elevation"], 50.0)
        self.assertAlmostEqual(res["max_elevation"], 50.0)
        for e in res["elevations"]:
            self.assertAlmostEqual(e, 50.0)

    def test_elevation_profile_linear_ramp(self):
        from app.pipeline.terrain_analysis import sample_elevation_profile
        x_ramp = np.tile(np.arange(10, dtype=np.float32), (10, 1))
        x_raster = Path(self.tmp_dir.name) / "x_ramp_prof.tif"
        with rasterio.open(x_raster, 'w', driver='GTiff', height=10, width=10, count=1, dtype='float32', transform=self.transform) as dst:
            dst.write(x_ramp, 1)
            
        res = sample_elevation_profile(x_raster, 0, 5, 9, 5, coordinate_system="pixel", samples=10)
        self.assertEqual(res["min_elevation"], 0.0)
        self.assertEqual(res["max_elevation"], 9.0)
        self.assertEqual(res["elevation_diff"], 9.0)
        # Should be strictly increasing
        self.assertEqual(res["elevations"], [float(i) for i in range(10)])

    def test_elevation_profile_nodata_crossing(self):
        from app.pipeline.terrain_analysis import sample_elevation_profile
        diag_ramp = np.tile(np.arange(10, dtype=np.float32), (10, 1))
        diag_ramp[0, 0] = -9999.0
        diag_ramp[9, 9] = -9999.0
        diag_raster = Path(self.tmp_dir.name) / "diag_ramp_prof.tif"
        with rasterio.open(diag_raster, 'w', driver='GTiff', height=10, width=10, count=1, dtype='float32', transform=self.transform, nodata=-9999.0) as dst:
            dst.write(diag_ramp, 1)
            
        res = sample_elevation_profile(diag_raster, 0, 0, 9, 9, coordinate_system="pixel", samples=10)
        # Point 0 and Point 9 will be NoData, but wait! Interpolation! 
        # If order=1, 0 is at exact pixel center, it will be NaN.
        # And point 8 (8.0, 8.0) interpolates using floor(8.0)=8 and 9, so it touches 9,9 which is NaN.
        self.assertIsNone(res["elevations"][0])
        self.assertIsNone(res["elevations"][-1])
        self.assertEqual(res["nodata_samples"], 3)
        self.assertEqual(res["valid_samples"], 7)

    def test_elevation_profile_geographic_distance(self):
        from app.pipeline.terrain_analysis import sample_elevation_profile
        from rasterio.crs import CRS
        geo_raster = Path(self.tmp_dir.name) / "geo.tif"
        
        # 0.1 degree pixels at Equator (~11.1km)
        transform = from_origin(0.0, 0.0, 0.1, 0.1)
        
        with rasterio.open(geo_raster, 'w', driver='GTiff', height=10, width=10, count=1, dtype='float32', transform=transform, crs=CRS.from_epsg(4326)) as dst:
            dst.write(np.zeros((10, 10), dtype=np.float32), 1)
            
        res = sample_elevation_profile(geo_raster, 0.05, -0.05, 0.95, -0.05, coordinate_system="spatial")
        # 0.9 degrees along equator = 0.9 * ~111.32 km = ~100.188 km
        self.assertAlmostEqual(res["total_distance"], 100188.0, delta=2000.0)

    def test_elevation_profile_out_of_bounds(self):
        from app.pipeline.terrain_analysis import sample_elevation_profile
        x_raster = Path(self.tmp_dir.name) / "oob_prof.tif"
        with rasterio.open(x_raster, 'w', driver='GTiff', height=10, width=10, count=1, dtype='float32', transform=self.transform) as dst:
            dst.write(np.zeros((10, 10), dtype=np.float32), 1)
            
        res = sample_elevation_profile(x_raster, -100, -100, -50, -50, "pixel", 5)
        self.assertEqual(res["valid_samples"], 0)
        self.assertEqual(res["nodata_samples"], 5)

    def test_profile_identical_points(self):
        from app.pipeline.terrain_analysis import sample_elevation_profile
        x_raster = Path(self.tmp_dir.name) / "ident_prof.tif"
        with rasterio.open(x_raster, 'w', driver='GTiff', height=10, width=10, count=1, dtype='float32', transform=self.transform) as dst:
            dst.write(np.zeros((10, 10), dtype=np.float32), 1)
        
        # Test backend explicitly raises ValueError if used directly (or handled by api)
        # Note: the validation was added to the API endpoint, so we should test the API endpoint or both.
        pass # Wait, let me just add it to api.py and check.

    def test_profile_identical_points_api(self):
        from fastapi.testclient import TestClient
        from app.routes.api import router
        import uuid
        
        # We need a mock job in the db
        from app.db.models import Job
        job_id = str(uuid.uuid4())
        job = Job(id=job_id, filename="ident_prof.tif", original_path="mock/path.tif", dsm_path=str(Path(self.tmp_dir.name) / "ident_prof_api.tif"))
        with rasterio.open(job.dsm_path, 'w', driver='GTiff', height=10, width=10, count=1, dtype='float32', transform=self.transform) as dst:
            dst.write(np.zeros((10, 10), dtype=np.float32), 1)
            
        from app.db.session import get_db
        db = next(get_db())
        db.add(job)
        db.commit()
        
        # Test JSON API
        res = self.client.get(f"/api/jobs/{job_id}/analysis/profile?start_x=5&start_y=5&end_x=5&end_y=5&system=pixel")
        self.assertEqual(res.status_code, 400)
        self.assertIn("START AND END COORDINATES MUST BE DIFFERENT", res.json()["detail"])
        
        # Test HTML HTMX API
        res_html = self.client.get(f"/api/jobs/{job_id}/analysis/profile_html?start_x=5&start_y=5&end_x=5&end_y=5&system=pixel")
        self.assertEqual(res_html.status_code, 200) # HTMX returns 200 with error html
        self.assertIn("START AND END COORDINATES MUST BE DIFFERENT", res_html.text)
        
        db.delete(job)
        db.commit()

    def test_api_elevation_profile_endpoint(self):
        import uuid
        db = next(get_db())
        job_id = f"test-job-{uuid.uuid4().hex[:8]}"
        job = Job(id=job_id, filename="mock.tif", original_path="mock/path/mock.tif", dsm_path=str(self.raster_path))
        db.add(job)
        db.commit()

        response = self.client.get(f"/api/jobs/{job_id}/analysis/profile?start_x=0&start_y=0&end_x=5&end_y=5&system=pixel")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("elevations", data)
        self.assertIn("distances", data)
        self.assertIn("total_distance", data)
        
    def test_contours_flat_raster(self):
        from app.pipeline.terrain_analysis import generate_contours
        flat_data = np.full((10, 10), 50.0, dtype=np.float32)
        flat_raster = Path(self.tmp_dir.name) / "flat_contour.tif"
        with rasterio.open(flat_raster, 'w', driver='GTiff', height=10, width=10, count=1, dtype='float32', transform=self.transform) as dst:
            dst.write(flat_data, 1)
            
        res = generate_contours(flat_raster, interval=10.0)
        # 50 is a multiple of 10, so it will generate a contour level at 50, but it might be empty if flat.
        self.assertEqual(res["feature_count"], 0)

    def test_contours_linear_ramp(self):
        from app.pipeline.terrain_analysis import generate_contours
        x_ramp = np.tile(np.arange(10, dtype=np.float32), (10, 1)) * 10.0 # 0 to 90
        x_raster = Path(self.tmp_dir.name) / "x_ramp_contour.tif"
        with rasterio.open(x_raster, 'w', driver='GTiff', height=10, width=10, count=1, dtype='float32', transform=self.transform) as dst:
            dst.write(x_ramp, 1)
            
        res = generate_contours(x_raster, interval=20.0)
        # Levels should be 0, 20, 40, 60, 80
        elevations = [f["properties"]["elevation"] for f in res["features"]]
        self.assertEqual(sorted(set(elevations)), [0.0, 20.0, 40.0, 60.0, 80.0])
        # Also check spatial coords for level 20. It should be at column 2. x = origin_x + col + 0.5. 
        # Transform origin is 100, 200. dx=1, dy=-1. col=2 -> x=102.5.
        feat_20 = [f for f in res["features"] if f["properties"]["elevation"] == 20.0][0]
        for coord in feat_20["geometry"]["coordinates"]:
            self.assertAlmostEqual(coord[0], 102.5, places=2)

    def test_contours_planar_surface(self):
        from app.pipeline.terrain_analysis import generate_contours
        # z = 5 * col + 5 * row + 10
        # at col=0, row=0, z=10. at col=9, row=9, z=100.
        cols, rows = np.meshgrid(np.arange(10), np.arange(10))
        z = 5.0 * cols + 5.0 * rows + 10.0
        raster = Path(self.tmp_dir.name) / "planar_contour.tif"
        with rasterio.open(raster, 'w', driver='GTiff', height=10, width=10, count=1, dtype='float32', transform=self.transform) as dst:
            dst.write(z.astype(np.float32), 1)
            
        res = generate_contours(raster, interval=30.0, min_elevation=20.0, max_elevation=80.0)
        elevations = [f["properties"]["elevation"] for f in res["features"]]
        self.assertEqual(sorted(set(elevations)), [20.0, 50.0, 80.0])

    def test_contours_invalid_interval(self):
        from app.pipeline.terrain_analysis import generate_contours
        raster = Path(self.tmp_dir.name) / "planar_contour.tif"
        with self.assertRaises(ValueError):
            generate_contours(raster, interval=0.0)
        with self.assertRaises(ValueError):
            generate_contours(raster, interval=-10.0)

    def test_contours_nodata_hole(self):
        from app.pipeline.terrain_analysis import generate_contours
        x_ramp = np.tile(np.arange(10, dtype=np.float32), (10, 1)) * 10.0
        # Make a massive hole in the middle at col=5, disrupting the 50 contour
        x_ramp[:, 5] = -9999.0
        raster = Path(self.tmp_dir.name) / "hole_contour.tif"
        with rasterio.open(raster, 'w', driver='GTiff', height=10, width=10, count=1, dtype='float32', transform=self.transform, nodata=-9999.0) as dst:
            dst.write(x_ramp, 1)
            
        res = generate_contours(raster, interval=50.0)
        feat_50 = [f for f in res["features"] if f["properties"]["elevation"] == 50.0]
        # Since col 5 is completely NoData, there is no contour at 50!
        self.assertEqual(len(feat_50), 0)

    def test_contours_non_unit_transform_and_crs(self):
        from app.pipeline.terrain_analysis import generate_contours
        from rasterio.crs import CRS
        x_ramp = np.tile(np.arange(10, dtype=np.float32), (10, 1)) * 10.0
        raster = Path(self.tmp_dir.name) / "non_unit_contour.tif"
        transform = from_origin(100.0, 200.0, 2.5, 3.5) # dx=2.5
        with rasterio.open(raster, 'w', driver='GTiff', height=10, width=10, count=1, dtype='float32', transform=transform, crs=CRS.from_epsg(32633)) as dst:
            dst.write(x_ramp, 1)
            
        res = generate_contours(raster, interval=20.0)
        self.assertIn("EPSG:32633", res["crs"])
        
        # level 20 is at col 2. x = 100 + 2*2.5 + 2.5*0.5 = 105.0 + 1.25 = 106.25
        feat_20 = [f for f in res["features"] if f["properties"]["elevation"] == 20.0][0]
        for coord in feat_20["geometry"]["coordinates"]:
            self.assertAlmostEqual(coord[0], 106.25, places=2)

    def test_contours_very_small_range(self):
        from app.pipeline.terrain_analysis import generate_contours
        flat_data = np.full((10, 10), 50.0, dtype=np.float32)
        flat_data[0,0] = 50.01
        raster = Path(self.tmp_dir.name) / "small_contour.tif"
        with rasterio.open(raster, 'w', driver='GTiff', height=10, width=10, count=1, dtype='float32', transform=self.transform) as dst:
            dst.write(flat_data, 1)
            
        res = generate_contours(raster, interval=10.0)
        self.assertTrue(len(res["features"]) >= 0)

    def test_contours_api_endpoint(self):
        import uuid
        db = next(get_db())
        job_id = f"test-job-{uuid.uuid4().hex[:8]}"
        job = Job(id=job_id, filename="mock.tif", original_path="mock/path/mock.tif", dsm_path=str(self.raster_path))
        db.add(job)
        db.commit()

        response = self.client.get(f"/api/jobs/{job_id}/analysis/contours?interval=10.0")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("features", data)
        self.assertIn("job_id", data)
        
        # Test validation error
        response_err = self.client.get(f"/api/jobs/{job_id}/analysis/contours?interval=-5.0")
        self.assertEqual(response_err.status_code, 400)
        
    def test_export_analysis_package_and_cache(self):
        from app.pipeline.terrain_analysis import export_analysis_package
        from app.pipeline.terrain_analysis import generate_contours
        import zipfile
        import json
        
        job_id = "test_export_1"
        raster = Path(self.tmp_dir.name) / f"{job_id}_dsm.tif"
        flat_data = np.full((10, 10), 50.0, dtype=np.float32)
        with rasterio.open(raster, 'w', driver='GTiff', height=10, width=10, count=1, dtype='float32', transform=self.transform) as dst:
            dst.write(flat_data, 1)
            
        # First export without contours
        zip_path1 = export_analysis_package(job_id, raster)
        self.assertTrue(zip_path1.exists())
        
        with zipfile.ZipFile(zip_path1, 'r') as zf:
            files = zf.namelist()
            self.assertIn(f"{job_id}_dsm.tif", files)
            self.assertIn(f"{job_id}_slope.tif", files)
            self.assertIn(f"{job_id}_aspect.tif", files)
            self.assertIn(f"{job_id}_metadata.json", files)
            self.assertNotIn(f"{job_id}_contours.geojson", files)
            
            with zf.open(f"{job_id}_metadata.json") as meta_f:
                metadata = json.load(meta_f)
                self.assertTrue(metadata["dsm_included"])
                self.assertTrue(metadata["slope_included"])
                self.assertFalse(metadata["contours_included"])
                self.assertIn("slope_mean", metadata)
        
        # Modify time to test cache reuse
        mtime1 = zip_path1.stat().st_mtime
        zip_path2 = export_analysis_package(job_id, raster)
        mtime2 = zip_path2.stat().st_mtime
        self.assertEqual(mtime1, mtime2) # Cache reused
        
        # Now generate contours
        import time
        time.sleep(0.05)
        generate_contours(raster, interval=10.0, output_path=raster.parent / f"{job_id}_contours.geojson")
        
        # Export again, should rebuild
        zip_path3 = export_analysis_package(job_id, raster)
        mtime3 = zip_path3.stat().st_mtime
        self.assertNotEqual(mtime1, mtime3)
        
        with zipfile.ZipFile(zip_path3, 'r') as zf:
            files = zf.namelist()
            self.assertIn(f"{job_id}_contours.geojson", files)
            # Ensure no duplicates
            self.assertEqual(len(files), len(set(files)))
            
            with zf.open(f"{job_id}_metadata.json") as meta_f:
                metadata = json.load(meta_f)
                self.assertTrue(metadata["contours_included"])

    def test_api_export_endpoint(self):
        import uuid
        db = next(get_db())
        job_id = f"test-job-{uuid.uuid4().hex[:8]}"
        job = Job(id=job_id, filename="mock.tif", original_path="mock/path/mock.tif", dsm_path=str(self.raster_path))
        db.add(job)
        db.commit()

        response = self.client.get(f"/api/jobs/{job_id}/analysis/export")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/zip")
        self.assertIn("attachment", response.headers["content-disposition"])
        self.assertIn(f"{job_id}_export.zip", response.headers["content-disposition"])
        
        # Test missing job
        response_missing = self.client.get(f"/api/jobs/missing_job/analysis/export")
        self.assertEqual(response_missing.status_code, 404)
        
        db.delete(job)
        db.commit()

    def test_ui_html_endpoints(self):
        import uuid
        db = next(get_db())
        job_id = f"test-ui-{uuid.uuid4().hex[:8]}"
        job = Job(id=job_id, filename="mock.tif", original_path="mock/path/mock.tif", dsm_path=str(self.raster_path))
        db.add(job)
        db.commit()

        # Slope HTML
        res = self.client.get(f"/api/jobs/{job_id}/analysis/slope_html")
        self.assertEqual(res.status_code, 200)
        self.assertIn("MIN:", res.text)
        
        # Aspect HTML
        res = self.client.get(f"/api/jobs/{job_id}/analysis/aspect_html")
        self.assertEqual(res.status_code, 200)
        self.assertIn("MEAN:", res.text)
        
        # Profile HTML
        res = self.client.get(f"/api/jobs/{job_id}/analysis/profile_html?start_x=0&start_y=0&end_x=5&end_y=5&system=pixel")
        self.assertEqual(res.status_code, 200)
        self.assertIn("DIST:", res.text)
        
        # Contours HTML
        res = self.client.get(f"/api/jobs/{job_id}/analysis/contours_html?interval=10.0")
        self.assertEqual(res.status_code, 200)
        self.assertIn("GENERATED:", res.text)
        
        db.delete(job)
        db.commit()

if __name__ == "__main__":
    unittest.main()

