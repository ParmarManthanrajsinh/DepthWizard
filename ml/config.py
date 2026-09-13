import os
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RESULTS_DIR = BASE_DIR / "results"

# Standard Data Split Paths (for real paired datasets)
TRAIN_DIR = DATA_DIR / "train"
VAL_DIR = DATA_DIR / "validation"
TEST_DIR = DATA_DIR / "test"

# Subfolders for images and DEMs
TRAIN_IMAGES_DIR = TRAIN_DIR / "images"
TRAIN_DEM_DIR = TRAIN_DIR / "dem"

VAL_IMAGES_DIR = VAL_DIR / "images"
VAL_DEM_DIR = VAL_DIR / "dem"

TEST_IMAGES_DIR = TEST_DIR / "images"
TEST_DEM_DIR = TEST_DIR / "dem"

# Raw Dataset Root Configurations (overridable via environment variables)
POTSDAM_ROOT = Path(os.getenv("POTSDAM_ROOT", str(DATA_DIR / "potsdam_raw")))
VAIHINGEN_ROOT = Path(os.getenv("VAIHINGEN_ROOT", str(DATA_DIR / "vaihingen_raw")))

# Manifest File Paths
MANIFEST_PATH = DATA_DIR / "manifest.csv"
TILES_MANIFEST_PATH = DATA_DIR / "tiles_manifest.csv"

# Global Calibration & Training Artifact Paths
GLOBAL_CALIBRATION_PATH = RESULTS_DIR / "global_calibration.json"
CHECKPOINT_PATH = Path(os.getenv("CKPT_PATH", str(RESULTS_DIR / "best_checkpoint.pt")))
TRAINING_LOG_PATH = RESULTS_DIR / "training_log.json"

# Depth Anything V2 Backbone Model Configuration
DEPTH_MODEL_NAME = os.getenv(
    "DEPTH_MODEL_NAME",
    "depth-anything/Depth-Anything-V2-Small-hf"
)

# Device Configuration
def get_device() -> str:
    device_env = os.getenv("DEVICE")
    if device_env:
        return device_env
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"

DEVICE = get_device()

# ImageNet Standard Normalization Constants
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)

# Terrestrial Elevation Plausibility Bounds (Dead Sea -430m to Everest 8848m)
MIN_PLAUSIBLE_ELEVATION = float(os.getenv("MIN_PLAUSIBLE_ELEVATION", "-500.0"))
MAX_PLAUSIBLE_ELEVATION = float(os.getenv("MAX_PLAUSIBLE_ELEVATION", "9000.0"))

# Default Batch Size and DataLoader Settings
DEFAULT_BATCH_SIZE = int(os.getenv("DEFAULT_BATCH_SIZE", "1"))
DEFAULT_NUM_WORKERS = int(os.getenv("DEFAULT_NUM_WORKERS", "0"))

# Baseline Output File Path
BASELINE_RESULTS_PATH = RESULTS_DIR / "baseline_results.json"

# Ensure directories exist on module load
for directory in (
    DATA_DIR,
    TRAIN_DIR,
    TRAIN_IMAGES_DIR,
    TRAIN_DEM_DIR,
    VAL_DIR,
    VAL_IMAGES_DIR,
    VAL_DEM_DIR,
    TEST_DIR,
    TEST_IMAGES_DIR,
    TEST_DEM_DIR,
    RESULTS_DIR,
):
    directory.mkdir(parents=True, exist_ok=True)
