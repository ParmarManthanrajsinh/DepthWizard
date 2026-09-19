import os
from pathlib import Path
import shutil
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import SAMPLES_DIR, TEMPLATES_DIR, UPLOADS_DIR
from app.db.models import Job, JobStatus
from app.db.session import get_db
from app.pipeline.runner import run_pipeline_for_job

router = APIRouter(prefix="/api", tags=["API"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.post("/jobs", response_model=Dict[str, Any])
async def create_job(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    gcp_file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    """
    Upload an optical image or GeoTIFF and enqueue the elevation pipeline.
    Seamlessly returns HTMX partial if requested from UI form, else returns JSON.
    """
    job_id = str(uuid.uuid4())
    safe_filename = Path(file.filename or "upload.png").name
    dest_path = UPLOADS_DIR / f"{job_id}_{safe_filename}"

    # Save uploaded file
    with open(dest_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Save optional GCP CSV file if supplied
    if gcp_file and gcp_file.filename:
        gcp_dest = UPLOADS_DIR / f"{job_id}_gcps.csv"
        with open(gcp_dest, "wb") as buffer:
            shutil.copyfileobj(gcp_file.file, buffer)

    # Create job in database
    job = Job(
        id=job_id,
        filename=safe_filename,
        original_path=str(dest_path),
        status=JobStatus.PENDING.value,
        progress=5,
        current_step="Image uploaded. Queued for inference."
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Launch background worker
    background_tasks.add_task(run_pipeline_for_job, job_id)

    # Return HTML partial if requested via HTMX
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            request=request,
            name="partials/job_status.html",
            context={"job": job}
        )

    return job.to_dict()


@router.post("/jobs/sample", response_model=Dict[str, Any])
async def create_sample_job(
    background_tasks: BackgroundTasks,
    sample_name: str = Query(..., description="Name of bundled sample file"),
    db: Session = Depends(get_db)
):
    """
    Launch a pipeline run using one of the pre-packaged sample datasets.
    """
    sample_path = SAMPLES_DIR / sample_name
    if not sample_path.exists():
        # Try generating sample on the fly
        from scripts.generate_sample import generate_all_samples
        generate_all_samples()
        if not sample_path.exists():
            raise HTTPException(status_code=404, detail=f"Sample '{sample_name}' not found.")

    job_id = str(uuid.uuid4())
    dest_path = UPLOADS_DIR / f"{job_id}_{sample_name}"
    shutil.copy(sample_path, dest_path)

    job = Job(
        id=job_id,
        filename=sample_name,
        original_path=str(dest_path),
        status=JobStatus.PENDING.value,
        progress=5,
        current_step="Queued sample dataset..."
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(run_pipeline_for_job, job_id)
    return job.to_dict()


@router.get("/jobs", response_model=List[Dict[str, Any]])
def list_jobs(db: Session = Depends(get_db)):
    """Retrieve all jobs ordered by creation date."""
    jobs = db.query(Job).order_by(Job.created_at.desc()).all()
    return [j.to_dict() for j in jobs]


@router.get("/jobs/{job_id}", response_model=Dict[str, Any])
def get_job(job_id: str, db: Session = Depends(get_db)):
    """Get metadata, progress, and metrics for a specific job."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job.to_dict()


@router.get("/jobs/{job_id}/mesh")
def get_job_mesh(job_id: str, db: Session = Depends(get_db)):
    """Serve the generated binary glTF (.glb) terrain mesh for 3D viewers."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job or not job.mesh_path or not os.path.exists(job.mesh_path):
        raise HTTPException(status_code=404, detail="3D mesh not ready or not found.")
    return FileResponse(
        job.mesh_path,
        media_type="model/gltf-binary",
        filename=f"{job_id}_terrain.glb"
    )


@router.get("/jobs/{job_id}/dsm")
def get_job_dsm(job_id: str, db: Session = Depends(get_db)):
    """Download the calibrated DSM GeoTIFF."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job or not job.dsm_path or not os.path.exists(job.dsm_path):
        raise HTTPException(status_code=404, detail="DSM file not ready or not found.")
    return FileResponse(
        job.dsm_path,
        media_type="image/tiff",
        filename=f"{job_id}_dsm.tif"
    )


@router.get("/jobs/{job_id}/preview")
def get_job_preview(job_id: str, db: Session = Depends(get_db)):
    """Serve the 2D colorized hillshade/elevation relief preview PNG."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job or not job.preview_path or not os.path.exists(job.preview_path):
        raise HTTPException(status_code=404, detail="Preview not ready or not found.")
    return FileResponse(job.preview_path, media_type="image/png")


@router.get("/samples")
def get_samples():
    """List available pre-packaged sample imagery."""
    samples = []
    if SAMPLES_DIR.exists():
        for f in SAMPLES_DIR.iterdir():
            if f.is_file() and f.suffix.lower() in [".png", ".jpg", ".tif", ".tiff"]:
                samples.append({
                    "name": f.name,
                    "size_kb": round(f.stat().st_size / 1024, 1),
                    "is_geotiff": f.suffix.lower() in [".tif", ".tiff"]
                })
    return {"samples": samples}


@router.get("/jobs/{job_id}/analysis/point")
def get_job_point_elevation(
    job_id: str,
    x: float,
    y: float,
    system: str = "spatial",
    db: Session = Depends(get_db)
):
    """Query the absolute elevation at a specific point on the DSM."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if not job.dsm_path or not os.path.exists(job.dsm_path):
        raise HTTPException(status_code=404, detail="DSM file not ready or not found.")
        
    try:
        from app.pipeline.terrain_analysis import sample_elevation
        result = sample_elevation(job.dsm_path, x, y, coordinate_system=system)
        return result
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to sample elevation: {str(e)}")


@router.get("/jobs/{job_id}/analysis/slope")
def get_job_slope_analysis(job_id: str, db: Session = Depends(get_db)):
    """Generate and return terrain slope metadata and layer path."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if not job.dsm_path or not os.path.exists(job.dsm_path):
        raise HTTPException(status_code=404, detail="DSM file not ready or not found.")
        
    try:
        from app.pipeline.terrain_analysis import calculate_slope
        slope_path = Path(job.dsm_path).parent / f"{job_id}_slope.tif"
        
        if not slope_path.exists():
            result = calculate_slope(job.dsm_path, slope_path)
        else:
            # Recompute to return stats consistently for API
            result = calculate_slope(job.dsm_path, slope_path)
            
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to calculate slope: {str(e)}")


@router.get("/jobs/{job_id}/analysis/aspect")
def get_job_aspect_analysis(job_id: str, db: Session = Depends(get_db)):
    """Generate and return terrain aspect metadata and layer path."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if not job.dsm_path or not os.path.exists(job.dsm_path):
        raise HTTPException(status_code=404, detail="DSM file not ready or not found.")
        
    try:
        from app.pipeline.terrain_analysis import calculate_aspect
        aspect_path = Path(job.dsm_path).parent / f"{job_id}_aspect.tif"
        
        if not aspect_path.exists():
            result = calculate_aspect(job.dsm_path, aspect_path)
        else:
            result = calculate_aspect(job.dsm_path, aspect_path)
            
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to calculate aspect: {str(e)}")


@router.get("/jobs/{job_id}/analysis/profile")
def get_job_elevation_profile(
    job_id: str,
    start_x: float,
    start_y: float,
    end_x: float,
    end_y: float,
    system: str = "spatial",
    samples: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Query the absolute elevation profile along a line."""
    import math
    if not (math.isfinite(start_x) and math.isfinite(start_y) and math.isfinite(end_x) and math.isfinite(end_y)):
        raise HTTPException(status_code=400, detail="COORDINATES MUST BE FINITE NUMBERS")
    if start_x == end_x and start_y == end_y:
        raise HTTPException(status_code=400, detail="START AND END COORDINATES MUST BE DIFFERENT")

    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if not job.dsm_path or not os.path.exists(job.dsm_path):
        raise HTTPException(status_code=404, detail="DSM file not ready or not found.")
        
    try:
        from app.pipeline.terrain_analysis import sample_elevation_profile
        result = sample_elevation_profile(
            job.dsm_path,
            start_x, start_y, end_x, end_y,
            coordinate_system=system,
            samples=samples
        )
        return result
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to sample profile: {str(e)}")


@router.get("/jobs/{job_id}/analysis/contours")
def get_job_contours(
    job_id: str,
    interval: float,
    min_elevation: Optional[float] = None,
    max_elevation: Optional[float] = None,
    db: Session = Depends(get_db)
):
    """Generate GeoJSON contours from the DSM."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if not job.dsm_path or not os.path.exists(job.dsm_path):
        raise HTTPException(status_code=404, detail="DSM file not ready or not found.")
        
    try:
        from app.pipeline.terrain_analysis import generate_contours
        output_path = Path(job.dsm_path).parent / f"{job_id}_contours.geojson"
        
        result = generate_contours(
            job.dsm_path,
            interval=interval,
            min_elevation=min_elevation,
            max_elevation=max_elevation,
            output_path=output_path
        )
        
        # Merge job_id into result as required
        result["job_id"] = job_id
        return result
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate contours: {str(e)}")


@router.get("/jobs/{job_id}/analysis/export")
def get_job_export(job_id: str, db: Session = Depends(get_db)):
    """Export terrain analysis artifacts as a ZIP archive."""
    from fastapi.responses import FileResponse
    
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if not job.dsm_path or not os.path.exists(job.dsm_path):
        raise HTTPException(status_code=404, detail="DSM file not ready or not found.")
        
    try:
        from app.pipeline.terrain_analysis import export_analysis_package
        zip_path = export_analysis_package(job_id, job.dsm_path)
        
        return FileResponse(
            path=zip_path,
            filename=f"{job_id}_export.zip",
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={job_id}_export.zip"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create export package: {str(e)}")


@router.get("/jobs/{job_id}/analysis/slope_html")
def get_slope_html(job_id: str, db: Session = Depends(get_db)):
    from fastapi.responses import HTMLResponse
    try:
        res = get_job_slope_analysis(job_id, db)
        return HTMLResponse(f"""
        <div class="analysis-result">
            MIN: <span style="color:#fff">{res.get('min_slope', 'N/A')}°</span><br>
            MAX: <span style="color:#fff">{res.get('max_slope', 'N/A')}°</span><br>
            MEAN: <span style="color:#fff">{res.get('mean_slope', 'N/A')}°</span><br>
            STATUS: <span style="color:var(--color-accent-green);">READY</span>
        </div>
        """)
    except Exception as e:
        return HTMLResponse(f'<div class="analysis-result analysis-error">ERR: {str(e)}</div>')

@router.get("/jobs/{job_id}/analysis/aspect_html")
def get_aspect_html(job_id: str, db: Session = Depends(get_db)):
    from fastapi.responses import HTMLResponse
    try:
        res = get_job_aspect_analysis(job_id, db)
        return HTMLResponse(f"""
        <div class="analysis-result">
            MIN: <span style="color:#fff">{res.get('min_aspect', 'N/A')}°</span><br>
            MAX: <span style="color:#fff">{res.get('max_aspect', 'N/A')}°</span><br>
            MEAN: <span style="color:#fff">{res.get('mean_aspect', 'N/A')}°</span><br>
            STATUS: <span style="color:var(--color-accent-green);">READY</span>
        </div>
        """)
    except Exception as e:
        return HTMLResponse(f'<div class="analysis-result analysis-error">ERR: {str(e)}</div>')

@router.get("/jobs/{job_id}/analysis/profile_html")
def get_profile_html(job_id: str, start_x: float, start_y: float, end_x: float, end_y: float, system: str = "spatial", db: Session = Depends(get_db)):
    from fastapi.responses import HTMLResponse
    try:
        res = get_job_elevation_profile(job_id, start_x, start_y, end_x, end_y, system, None, db)
        min_e = res['min_elevation']
        max_e = res['max_elevation']
        dist = res['total_distance']
        # Simple SVG line chart
        svg = ""
        if len(res['distances']) > 1 and min_e is not None and max_e is not None:
            width = 280
            height = 80
            pts = []
            e_range = max(max_e - min_e, 0.1)
            for d, e in zip(res['distances'], res['elevations']):
                if e is not None:
                    cx = (d / dist) * width
                    cy = height - ((e - min_e) / e_range) * height
                    pts.append(f"{cx},{cy}")
            if pts:
                svg = f"""<svg width="100%" height="{height}" viewBox="0 0 {width} {height}" style="margin-top:4px; border:1px solid var(--color-rule); background:var(--color-paper-3);">
                    <polyline fill="none" stroke="var(--color-accent-green)" stroke-width="2" points="{' '.join(pts)}" />
                </svg>"""
        return HTMLResponse(f"""
        <div class="analysis-result">
            DIST: <span style="color:#fff">{dist} m</span><br>
            ELEV: <span style="color:#fff">{min_e} m - {max_e} m</span><br>
            {svg}
        </div>
        """)
    except HTTPException as he:
        return HTMLResponse(f'<div class="analysis-result analysis-error">ERR: {he.detail}</div>')
    except Exception as e:
        return HTMLResponse(f'<div class="analysis-result analysis-error">ERR: {str(e)}</div>')

@router.get("/jobs/{job_id}/analysis/contours_html")
def get_contours_html(job_id: str, interval: float, db: Session = Depends(get_db)):
    from fastapi.responses import HTMLResponse
    try:
        res = get_job_contours(job_id, interval, None, None, db)
        fc = res.get('feature_count', 0)
        return HTMLResponse(f"""
        <div class="analysis-result">
            GENERATED: <span style="color:#fff">{fc} LINES</span><br>
            <a href="/api/jobs/{job_id}/analysis/export" style="color:#00f0ff; text-decoration:underline;">[DOWNLOAD VIA EXPORT]</a>
        </div>
        """)
    except Exception as e:
        return HTMLResponse(f'<div class="analysis-result analysis-error">ERR: {str(e)}</div>')


