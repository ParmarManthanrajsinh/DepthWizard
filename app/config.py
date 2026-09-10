import os
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BASE_DIR / "app"
DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
OUTPUTS_DIR = DATA_DIR / "outputs"
SAMPLES_DIR = DATA_DIR / "samples"
STATIC_DIR = APP_DIR / "static"
TEMPLATES_DIR = APP_DIR / "templates"
CACHE_DIR = DATA_DIR / "cache"
DEM_CACHE_DIR = CACHE_DIR / "dem"

# Database Configuration
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR}/depthwizard.db")

# Elevation Pipeline Settings
DEPTH_MODEL_NAME = os.getenv(
    "DEPTH_MODEL_NAME",
    "depth-anything/Depth-Anything-V2-Small-hf"
)
# If True or if torch/transformers are missing, pipeline runs synthetic/mock estimator
USE_MOCK_MODEL = os.getenv("USE_MOCK_MODEL", "false").lower() in ("true", "1", "yes")

# Hardware Device Selection
DEVICE = os.getenv("DEVICE", "cuda" if os.getenv("CUDA_VISIBLE_DEVICES") else "cpu")

# Mesh Generation Settings
# 160x160 grid = 25,600 vertices / 50,000 triangles (smooth 60fps WebGL/WASM target)
MESH_GRID_RESOLUTION = int(os.getenv("MESH_GRID_RESOLUTION", "160"))
DEFAULT_HEIGHT_SCALE = float(os.getenv("DEFAULT_HEIGHT_SCALE", "35.0"))

# Server Settings
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# Ensure directory structure exists on import
for path in (DATA_DIR, UPLOADS_DIR, OUTPUTS_DIR, SAMPLES_DIR, DEM_CACHE_DIR):
    path.mkdir(parents=True, exist_ok=True)
