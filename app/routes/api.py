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
