from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import TEMPLATES_DIR
from app.db.models import Job
from app.db.session import get_db

router = APIRouter(tags=["Pages"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/", response_class=HTMLResponse)
def index_page(request: Request, db: Session = Depends(get_db)):
    """Main dashboard page."""
    jobs = db.query(Job).order_by(Job.created_at.desc()).limit(10).all()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"jobs": jobs}
    )


@router.get("/jobs/{job_id}/status", response_class=HTMLResponse)
def job_status_partial(request: Request, job_id: str, db: Session = Depends(get_db)):
    """HTMX polling partial for live pipeline progress."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return templates.TemplateResponse(
        request=request,
        name="partials/job_status.html",
        context={"job": job}
    )


@router.get("/viewer", response_class=HTMLResponse)
def viewer_page(request: Request, job: str = ""):
    """Full-screen 3D flythrough page."""
    return templates.TemplateResponse(
        request=request,
        name="viewer.html",
        context={"job_id": job}
    )


@router.get("/health")
def health_check():
    return {"status": "ok", "service": "DepthWizard"}
