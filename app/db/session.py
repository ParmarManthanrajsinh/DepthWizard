from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from app.config import DATABASE_URL
from app.db.models import Base

# Configure SQLite engine (check_same_thread=False for FastAPI concurrency)
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Create tables if they do not already exist, and ensure schema columns match."""
    Base.metadata.create_all(bind=engine)

    # Lightweight SQLite schema auto-migration
    if "sqlite" in DATABASE_URL:
        from sqlalchemy import text
        with engine.begin() as conn:
            result = conn.execute(text("PRAGMA table_info(jobs)")).fetchall()
            existing_cols = {row[1] for row in result}
            new_cols = [
                ("calibration_source", "VARCHAR(128) DEFAULT 'Unknown'"),
                ("is_synthetic_calibration", "BOOLEAN DEFAULT 0"),
                ("model_name", "VARCHAR(128) DEFAULT 'Depth Anything V2'"),
                ("mean_slope_deg", "FLOAT"),
                ("max_slope_deg", "FLOAT"),
                ("steep_terrain_pct", "FLOAT"),
            ]
            for col_name, col_type in new_cols:
                if col_name not in existing_cols:
                    conn.execute(text(f"ALTER TABLE jobs ADD COLUMN {col_name} {col_type}"))


def get_db() -> Generator[Session, None, None]:
    """Dependency for obtaining a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
