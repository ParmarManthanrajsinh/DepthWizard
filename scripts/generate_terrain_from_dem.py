import os
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np
from PIL import Image
import rasterio

from app.config import DATA_DIR, OUTPUTS_DIR, SAMPLES_DIR
from app.db.models import Job, JobStatus
from app.db.session import SessionLocal
from app.pipeline.mesh_builder import build_terrain_glb
from app.pipeline.geospatial import save_dsm_geotiff, generate_colorized_preview, compute_slope_profile


def generate_terrain_texture(elevation: np.ndarray) -> Image.Image:
    """
    Generate realistic hypsometric + hillshade optical texture from DEM elevation.
    """
    h_min, h_max = float(np.nanmin(elevation)), float(np.nanmax(elevation))
    h_norm = np.clip((elevation - h_min) / max(h_max - h_min, 1e-5), 0.0, 1.0)

    # Directional hillshade (sun from NW: azimuth 315 deg, altitude 45 deg)
    gy, gx = np.gradient(h_norm * 60.0)
    sun = np.array([-0.5, -0.5, 0.707], dtype=np.float32)
    sun /= np.linalg.norm(sun)
    normal = np.stack([-gx, -gy, np.ones_like(gx)], axis=-1)
    norm_len = np.linalg.norm(normal, axis=-1, keepdims=True)
    normal /= np.maximum(norm_len, 1e-6)

    diffuse = np.clip(np.sum(normal * sun, axis=-1), 0.2, 1.0)

    # Color ramp points (elevation fractions):
    # < 0.15: lowlands/valley emerald (45, 110, 60)
    # 0.15 - 0.45: midland pine/olive (80, 130, 65)
    # 0.45 - 0.75: rocky granite/slate (140, 135, 130)
    # > 0.75: snowy alpine peaks (245, 248, 255)
    c_low = np.array([45, 110, 60], dtype=np.float32)
    c_mid = np.array([85, 130, 70], dtype=np.float32)
    c_rock = np.array([145, 140, 135], dtype=np.float32)
    c_snow = np.array([245, 248, 255], dtype=np.float32)

    w_mid = np.clip((h_norm - 0.15) / 0.30, 0.0, 1.0)[:, :, None]
    w_rock = np.clip((h_norm - 0.45) / 0.30, 0.0, 1.0)[:, :, None]
    w_snow = np.clip((h_norm - 0.75) / 0.20, 0.0, 1.0)[:, :, None]

    base = c_low * (1.0 - w_mid) + c_mid * w_mid
    base = base * (1.0 - w_rock) + c_rock * w_rock
    base = base * (1.0 - w_snow) + c_snow * w_snow

    shaded = base * diffuse[:, :, None]
    uint8_img = np.clip(shaded, 0, 255).astype(np.uint8)
    return Image.fromarray(uint8_img, mode="RGB")


def process_dem_file(dem_path_str: str, job_id: str = "dem_90m_shasta") -> dict:
    dem_path = Path(dem_path_str)
    if not dem_path.exists():
        raise FileNotFoundError(f"Input DEM not found: {dem_path}")

    # Copy to project samples
    sample_dest = SAMPLES_DIR / dem_path.name
    if not sample_dest.exists() or sample_dest != dem_path:
        shutil.copy2(dem_path, sample_dest)
        print(f"Copied DEM to: {sample_dest}")

    # Read DEM metadata & data
    with rasterio.open(dem_path) as src:
        crs_str = str(src.crs) if src.crs else "EPSG:3857"
        bounds = {
            "left": src.bounds.left,
            "bottom": src.bounds.bottom,
            "right": src.bounds.right,
            "top": src.bounds.top,
        }
        raw_dem = src.read(1).astype(np.float32)
        # Handle nodata if present
        if src.nodata is not None:
            raw_dem[raw_dem == src.nodata] = np.nan
        src_w, src_h = src.width, src.height

    print(f"Loaded DEM: {src_w}x{src_h}, CRS: {crs_str}, Range: [{np.nanmin(raw_dem):.1f}m, {np.nanmax(raw_dem):.1f}m]")

    # Resample to 1024x1024 for high-fidelity terrain & 60 FPS Raylib WASM flight
    target_res = 1024
    pil_dem = Image.fromarray(raw_dem)
    pil_resampled = pil_dem.resize((target_res, target_res), resample=Image.Resampling.BILINEAR)
    dem_resampled = np.asarray(pil_resampled, dtype=np.float32)

    # 1. Generate realistic terrain texture
    texture_img = generate_terrain_texture(dem_resampled)
    print(f"Generated terrain texture: {texture_img.size}")

    # 2. Build 3D glTF (.glb) terrain mesh
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    mesh_filename = f"{job_id}_terrain.glb"
    mesh_path = OUTPUTS_DIR / mesh_filename
    build_terrain_glb(
        elevation_map=dem_resampled,
        texture_image=texture_img,
        output_path=mesh_path,
        grid_resolution=256,
        height_scale=95.0,
        physical_span=650.0,
        feather_fraction=0.08,
        feather_rim_y=-1.0,
    )
    print(f"Exported 3D mesh: {mesh_path} ({mesh_path.stat().st_size / 1024:.1f} KB)")

    # 3. Export DSM GeoTIFF
    dsm_filename = f"{job_id}_dsm.tif"
    dsm_path = OUTPUTS_DIR / dsm_filename
    save_dsm_geotiff(
        elevation_map=dem_resampled,
        output_path=dsm_path,
        crs_str=crs_str,
        bounds=bounds,
    )
    print(f"Saved DSM GeoTIFF: {dsm_path}")

    # 4. Export Hillshade Preview PNG
    preview_filename = f"{job_id}_preview.png"
    preview_path = OUTPUTS_DIR / preview_filename
    generate_colorized_preview(
        elevation_map=dem_resampled,
        output_path=preview_path,
    )
    print(f"Saved Color Relief Preview: {preview_path}")

    # 5. Compute slope metrics
    slope_metrics = compute_slope_profile(dem_resampled)

    # 6. Register/Update Job in SQLite database
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            job = Job(id=job_id)
            db.add(job)

        job.filename = dem_path.name
        job.original_path = str(sample_dest)
        job.status = JobStatus.COMPLETED.value
        job.progress = 100
        job.current_step = "Completed"
        job.is_georeferenced = True
        job.crs = crs_str
        job.model_name = "Direct Ground-Truth DEM (90m SRTM)"
        job.elevation_min = float(np.nanmin(dem_resampled))
        job.elevation_max = float(np.nanmax(dem_resampled))
        job.rmse = 0.0
        job.mae = 0.0
        job.correlation = 1.0
        job.calibration_source = "True Surface DEM"
        job.is_synthetic_calibration = False
        job.mean_slope_deg = slope_metrics["mean_slope_deg"]
        job.max_slope_deg = slope_metrics["max_slope_deg"]
        job.steep_terrain_pct = slope_metrics["steep_terrain_pct"]
        job.dsm_path = str(dsm_path)
        job.mesh_path = str(mesh_path)
        job.preview_path = str(preview_path)
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        print(f"Registered Job in DB: id={job_id}")
    finally:
        db.close()

    return {
        "job_id": job_id,
        "mesh_path": str(mesh_path),
        "dsm_path": str(dsm_path),
        "preview_path": str(preview_path),
        "elevation_min": float(np.nanmin(dem_resampled)),
        "elevation_max": float(np.nanmax(dem_resampled)),
        "crs": crs_str,
    }


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\Administrator\Downloads\ABDM\Pictures\dem_90m.tif"
    res = process_dem_file(path)
    print("\nSUCCESS! Results:", res)
