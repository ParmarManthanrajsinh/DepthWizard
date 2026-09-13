from datetime import datetime, timezone
import logging
from pathlib import Path
from PIL import Image

from app.config import OUTPUTS_DIR, UPLOADS_DIR, USE_MOCK_MODEL
from app.db.models import Job, JobStatus
from app.db.session import SessionLocal
from app.pipeline.calibration import calibrate_elevation
from app.pipeline.estimator import DepthAnythingV2Estimator, MockDepthEstimator
from app.pipeline.geospatial import (
    generate_colorized_preview,
    inspect_georeference,
    save_dsm_geotiff,
)
from app.pipeline.mesh_builder import build_terrain_glb

logger = logging.getLogger("depthwizard.pipeline.runner")


def run_pipeline_for_job(job_id: str) -> None:
    """
    Execute end-to-end elevation estimation and 3D mesh generation for a given job.
    Designed to run asynchronously in FastAPI BackgroundTasks or directly.
    """
    db = SessionLocal()
    job: Job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        logger.error(f"Job {job_id} not found in database.")
        db.close()
        return

    try:
        # Step 1: Initialization & Geospatial Metadata
        job.status = JobStatus.PROCESSING.value
        job.progress = 15
        job.current_step = "Analyzing spatial metadata and CRS..."
        db.commit()

        input_path = Path(job.original_path)
        is_geo, crs_str, bounds = inspect_georeference(input_path)
        job.is_georeferenced = is_geo
        job.crs = crs_str
        db.commit()

        # Step 2: Monocular Depth Inference
        job.progress = 40
        job.current_step = "Estimating depth map..."
        db.commit()

        with Image.open(input_path) as raw_img:
            rgb_img = raw_img.convert("RGB")
            estimator = DepthAnythingV2Estimator()
            # Optional manual mock override for local dev (app/config.py).
            # applied BEFORE inference; label below still derives from the
            # estimator's actual reported outcome, so the UI badge stays honest
            # in both paths.
            if USE_MOCK_MODEL:
                estimator.force_mock()
            relative_depth = estimator.estimate(rgb_img)
            # Derive label from ACTUAL outcome, never assume real model ran.
            # estimate() silently falls back to MockDepthEstimator on load or
            # inference failure; labeling that as real would be fake data
            # presented as real (same class of bug as the RMSE fix).
            if estimator.used_fallback:
                model_label = "Mock Dev Mode"
                logger.warning(
                    f"Job {job_id}: real depth model unavailable; "
                    "falling back to MockDepthEstimator. Job labeled 'Mock Dev Mode'."
                )
            else:
                model_label = "Depth Anything V2 (PyTorch)"
            job.model_name = model_label
            db.commit()

        # Step 3: Scale Calibration (SRTM / GCP / Metric Fit)
        job.progress = 65
        job.current_step = "Calibrating elevation scale against reference DEM or GCPs..."
        db.commit()

        # Check for optional Ground Control Points (GCPs) file
        gcp_path = UPLOADS_DIR / f"{job_id}_gcps.csv"
        gcps = None
        if gcp_path.exists():
            from app.pipeline.calibration import parse_gcp_csv
            try:
                gcps = parse_gcp_csv(gcp_path.read_text(encoding="utf-8"))
                logger.info(f"Loaded {len(gcps)} GCP points from {gcp_path.name}")
            except Exception as ex:
                logger.warning(f"Failed to parse GCP file {gcp_path}: {ex}")

        calib = calibrate_elevation(
            relative_depth=relative_depth,
            is_georeferenced=is_geo,
            bounds=bounds,
            gcps=gcps,
        )

        job.rmse = calib.rmse
        job.mae = calib.mae
        job.correlation = calib.correlation
        job.elevation_min = calib.elevation_min
        job.elevation_max = calib.elevation_max
        job.calibration_source = calib.calibration_source
        job.is_synthetic_calibration = calib.is_synthetic

        from app.pipeline.geospatial import compute_slope_profile
        slope_metrics = compute_slope_profile(calib.calibrated_elevation)
        job.mean_slope_deg = slope_metrics["mean_slope_deg"]
        job.max_slope_deg = slope_metrics["max_slope_deg"]
        job.steep_terrain_pct = slope_metrics["steep_terrain_pct"]

        db.commit()

        # Step 4: Export DSM GeoTIFF and Colorized Hillshade Preview
        job.progress = 80
        job.current_step = "Generating DSM GeoTIFF and color relief preview..."
        db.commit()

        dsm_filename = f"{job_id}_dsm.tif"
        dsm_path = OUTPUTS_DIR / dsm_filename
        save_dsm_geotiff(
            elevation_map=calib.calibrated_elevation,
            output_path=dsm_path,
            crs_str=crs_str,
            bounds=bounds,
        )
        job.dsm_path = str(dsm_path)

        preview_filename = f"{job_id}_preview.png"
        preview_path = OUTPUTS_DIR / preview_filename
        generate_colorized_preview(
            elevation_map=calib.calibrated_elevation,
            output_path=preview_path,
        )
        job.preview_path = str(preview_path)
        db.commit()

        # Step 5: Triangulate Heightfield and Export GLB Mesh with UV Texture
        job.progress = 90
        job.current_step = "Building 3D terrain mesh and projecting texture..."
        db.commit()

        mesh_filename = f"{job_id}_terrain.glb"
        mesh_path = OUTPUTS_DIR / mesh_filename
        build_terrain_glb(
            elevation_map=calib.calibrated_elevation,
            texture_image=rgb_img,
            output_path=mesh_path,
        )
        job.mesh_path = str(mesh_path)

        # Step 6: Completion
        job.progress = 100
        job.status = JobStatus.COMPLETED.value
        job.current_step = "Completed"
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        logger.info(f"Job {job_id} successfully completed.")

    except Exception as e:
        logger.exception(f"Pipeline execution failed for job {job_id}: {e}")
        job.status = JobStatus.FAILED.value
        job.current_step = "Failed"
        job.error_message = str(e)
        db.commit()
    finally:
        db.close()
