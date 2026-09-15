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
OPENTOPOGRAPHY_API_KEY = os.getenv("OPENTOPOGRAPHY_API_KEY", "")


def is_real_model_available() -> bool:
    """Check if PyTorch & transformers are present in environment."""
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
        return True
    except ImportError:
        return False


def get_device() -> str:
    device_env = os.getenv("DEVICE")
    if device_env:
        return device_env
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


# Hardware Device Selection
DEVICE = get_device()

# Mesh Generation Settings
# 160x160 grid = 25,600 vertices / 50,000 triangles (smooth 60fps WebGL/WASM target)
MESH_GRID_RESOLUTION = int(os.getenv("MESH_GRID_RESOLUTION", "160"))
DEFAULT_HEIGHT_SCALE = float(os.getenv("DEFAULT_HEIGHT_SCALE", "35.0"))

# Sea / shoreline settings (must match engine/src/world.h defaults).
# SEA_LEVEL_Y: engine water plane height. BEACH_LIFT_M: interior mesh minimum,
# kept above max wave crest (SEA_LEVEL_Y + 0.13m swell) so low-relief tiles
# never render submerged ("sea overlaps terrain" fix).
SEA_LEVEL_Y = float(os.getenv("SEA_LEVEL_Y", "1.5"))
SEABED_LEVEL_Y = float(os.getenv("SEABED_LEVEL_Y", "-5.5"))
BEACH_LIFT_M = float(os.getenv("BEACH_LIFT_M", "2.5"))
FEATHER_RIM_Y = float(os.getenv("FEATHER_RIM_Y", "-1.0"))

# Server Settings
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# Ensure directory structure exists on import
for path in (DATA_DIR, UPLOADS_DIR, OUTPUTS_DIR, SAMPLES_DIR, DEM_CACHE_DIR):
    path.mkdir(parents=True, exist_ok=True)
