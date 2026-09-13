"""
DepthWizard ML Module (SIH 2026 - SIH26175)
Provides PyTorch Dataset, Preprocessing, Depth Anything V2 Baseline Inference,
and Ground-Truth DEM Evaluation utilities.
"""

from ml.config import (
    DATA_DIR,
    TRAIN_DIR,
    VAL_DIR,
    TEST_DIR,
    RESULTS_DIR,
    DEPTH_MODEL_NAME,
    DEVICE,
)

__all__ = [
    "DATA_DIR",
    "TRAIN_DIR",
    "VAL_DIR",
    "TEST_DIR",
    "RESULTS_DIR",
    "DEPTH_MODEL_NAME",
    "DEVICE",
    "normalize_image",
    "create_dem_valid_mask",
    "align_dem_to_image",
    "prepare_image_tensor",
    "prepare_dem_tensor",
    "SatelliteElevationDataset",
    "DepthAnythingV2Baseline",
    "compute_mae",
    "compute_rmse",
    "compute_pearson_correlation",
    "evaluate_baseline",
]


def __getattr__(name: str):
    if name in (
        "normalize_image",
        "create_dem_valid_mask",
        "align_dem_to_image",
        "prepare_image_tensor",
        "prepare_dem_tensor",
    ):
        import ml.preprocessing as prep
        return getattr(prep, name)
    if name == "SatelliteElevationDataset":
        from ml.dataset import SatelliteElevationDataset
        return SatelliteElevationDataset
    if name == "DepthAnythingV2Baseline":
        from ml.inference import DepthAnythingV2Baseline
        return DepthAnythingV2Baseline
    if name in (
        "compute_mae",
        "compute_rmse",
        "compute_pearson_correlation",
        "evaluate_baseline",
    ):
        import ml.evaluate as ev
        return getattr(ev, name)
    raise AttributeError(f"module 'ml' has no attribute '{name}'")
