import enum
from datetime import datetime, timezone
from typing import Any, Dict
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class JobStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    original_path = Column(String(512), nullable=False)
    
    # Geospatial metadata
    is_georeferenced = Column(Boolean, default=False)
    crs = Column(String(64), nullable=True)
    bounds_geojson = Column(Text, nullable=True)

    # State & progress
    status = Column(String(32), default=JobStatus.PENDING.value, index=True)
    progress = Column(Integer, default=0)
    current_step = Column(String(128), default="Queued")

    # Accuracy Metrics (SIH Grading Criterion: 50% DSM accuracy)
    rmse = Column(Float, nullable=True)
    mae = Column(Float, nullable=True)
    correlation = Column(Float, nullable=True)
    elevation_min = Column(Float, nullable=True)
    elevation_max = Column(Float, nullable=True)

    # Generated Artifacts
    dsm_path = Column(String(512), nullable=True)
    mesh_path = Column(String(512), nullable=True)
    preview_path = Column(String(512), nullable=True)
    
    # Error tracking
    error_message = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "filename": self.filename,
            "is_georeferenced": self.is_georeferenced,
            "crs": self.crs,
            "status": self.status,
            "progress": self.progress,
            "current_step": self.current_step,
            "metrics": {
                "rmse": round(self.rmse, 3) if self.rmse is not None else None,
                "mae": round(self.mae, 3) if self.mae is not None else None,
                "correlation": round(self.correlation, 3) if self.correlation is not None else None,
                "elevation_min": round(self.elevation_min, 2) if self.elevation_min is not None else None,
                "elevation_max": round(self.elevation_max, 2) if self.elevation_max is not None else None,
            },
            "artifacts": {
                "dsm_url": f"/api/jobs/{self.id}/dsm" if self.dsm_path else None,
                "mesh_url": f"/api/jobs/{self.id}/mesh" if self.mesh_path else None,
                "preview_url": f"/api/jobs/{self.id}/preview" if self.preview_path else None,
            },
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
