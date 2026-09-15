from datetime import datetime, timezone
import logging
from pathlib import Path
from PIL import Image

from app.config import OUTPUTS_DIR, UPLOADS_DIR
from app.db.models import Job, JobStatus
from app.db.session import SessionLocal
from app.pipeline.calibration import calibrate_elevation
from app.pipeline.estimator import DepthAnythingV2Estimator, MockDepthEstimator, get_depth_estimator
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

        # Safely load RGB image or single-band elevation GeoTIFF
        try:
            import rasterio
            with rasterio.open(input_path) as src:
                if src.count == 1:
                    import numpy as np
                    raw_band = src.read(1).astype(np.float32)
                    if src.nodata is not None:
                        raw_band[raw_band == src.nodata] = np.nan
                    b_min, b_max = float(np.nanmin(raw_band)), float(np.nanmax(raw_band))
                    if b_max > b_min:
                        norm_band = np.clip((raw_band - b_min) / (b_max - b_min), 0.0, 1.0)
                    else:
                        norm_band = np.zeros_like(raw_band)
                    rgb_img = Image.fromarray((norm_band * 255.0).astype(np.uint8)).convert("RGB")
                else:
                    with Image.open(input_path) as raw_img:
                        rgb_img = raw_img.convert("RGB")
        except Exception:
            with Image.open(input_path) as raw_img:
                rgb_img = raw_img.convert("RGB")

        estimator = get_depth_estimator()
        metric_agl = estimator.estimate(rgb_img)

        # model_name derived AFTER estimate() from actual outcome, never assumed.
        if estimator.used_fallback or isinstance(estimator, MockDepthEstimator):
            model_label = "Mock Dev Mode"
        elif estimator.__class__.__name__ == "DepthWizard03BEstimator" and not getattr(
            estimator, "used_pretrained_fallback", False
        ):
            model_label = "DepthWizard-05-R1 (fine-tuned)"
        else:
            model_label = "Depth Anything V2 (pretrained, fallback)"

        job.model_name = model_label
        db.commit()

        # Ex04B: Semantic / Object Exclusion for Terrain Reconstruction
        # DISABLED in production — ablation study (docs/experiments/EXPERIMENT_04B_REPORT.md) showed
        # EX04B+EX04A produces worse gradients (2.16 vs 1.40) and worse MAE (3.36 vs
        # 3.22) than EX04A alone across 39 scenes. Kept for research; enable via
        # EX04B_CONFIG["enabled"] = True.
        # from app.pipeline.ex04b_semantic_mask import apply_ex04b_conditioning
        # metric_agl, ex04b_stats = apply_ex04b_conditioning(metric_agl)

        # Ex04A: Terrain Geometry Stabilization & Depth-to-Elevation Conditioning
        from app.pipeline.ex04a_conditioning import apply_ex04a_conditioning
        metric_agl, ex04a_stats = apply_ex04a_conditioning(metric_agl)
        logger.info(f"Ex04A Conditioning applied. Max gradient reduced from {ex04a_stats['max_gradient_before']:.2f} to {ex04a_stats['max_gradient_after']:.2f}")

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
            relative_depth=metric_agl,
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
        import numpy as np
        logger.info(f"Final DSM Range: Min={np.nanmin(calib.calibrated_elevation):.2f}m, Max={np.nanmax(calib.calibrated_elevation):.2f}m")
        
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
        job.error_message = None
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        logger.info(f"Job {job_id} successfully completed.")

    except Exception as e:
        logger.exception(f"Pipeline execution failed for job {job_id}: {e}")
        job.status = JobStatus.FAILED.value
        job.current_step = "Failed"
        job.error_message = str(e)
        # Never leave a success-implying label on a job with no real result.
        # model_label only exists when estimate() completed; otherwise mark miss.
        try:
            model_label  # noqa: B018
        except NameError:
            job.model_name = "Failed before inference"
        db.commit()
    finally:
        db.close()
