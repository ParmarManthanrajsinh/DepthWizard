import logging
from typing import Any, Dict, Optional, Tuple, Union
import numpy as np
from PIL import Image

try:
    import torch
except ImportError:
    torch = None  # type: ignore

from pathlib import Path
from ml.config import CHECKPOINT_PATH, DEPTH_MODEL_NAME, DEVICE
from app.pipeline.calibration import fit_linear_scale_offset
from app.pipeline.estimator import DepthAnythingV2Estimator, MockDepthEstimator

logger = logging.getLogger("depthwizard.ml.inference")


class DepthAnythingV2Baseline:
    """
    Inference wrapper for the Depth Anything V2 monocular foundation model.
    Directly reuses DepthWizard's DepthAnythingV2Estimator backbone.

    IMPORTANT ARCHITECTURAL DISTINCTION:
    - Raw Depth Anything V2 produces DIMENSIONLESS RELATIVE DEPTH.
    - Raw predictions MUST NOT be reported as absolute elevation in meters.
    - Metric elevation requires affine calibration (h_metric = a * d_rel + b).
    - In production, calibration uses frozen global affine (a, b) or sparse GCPs.
    """

    def __init__(
        self,
        model_name: str = DEPTH_MODEL_NAME,
        device: str = DEVICE,
        force_mock: Optional[bool] = None,
        checkpoint_path: Optional[Union[str, Path]] = None,
    ):
        self.model_name = model_name
        self.device = device

        if force_mock:
            logger.info("Initializing DepthAnythingV2Baseline with MockDepthEstimator (development mode).")
            self.estimator = MockDepthEstimator()
        else:
            self.estimator = DepthAnythingV2Estimator(model_name=model_name, device=device)

        # Auto-load checkpoint if specified or found
        ckpt_candidate = Path(checkpoint_path) if checkpoint_path else CHECKPOINT_PATH
        if ckpt_candidate and ckpt_candidate.exists():
            self.load_checkpoint(ckpt_candidate)

    def load_checkpoint(self, checkpoint_path: Union[str, Path]) -> bool:
        """Load fine-tuned weights into DepthAnythingV2 model."""
        ckpt_p = Path(checkpoint_path)
        if not ckpt_p.exists():
            logger.warning(f"Checkpoint {ckpt_p} not found.")
            return False
        if isinstance(self.estimator, DepthAnythingV2Estimator):
            self.estimator._load()
            if self.estimator._model is not None and torch is not None:
                try:
                    logger.info(f"Loading checkpoint weights from {ckpt_p}...")
                    state = torch.load(ckpt_p, map_location=self.device, weights_only=True)
                    if isinstance(state, dict) and "model_state_dict" in state:
                        state = state["model_state_dict"]
                    missing, unexpected = self.estimator._model.load_state_dict(state, strict=False)
                    logger.info(f"Loaded checkpoint {ckpt_p.name} (missing={len(missing)}, unexpected={len(unexpected)}).")
                    return True
                except Exception as e:
                    logger.error(f"Failed loading checkpoint {ckpt_p}: {e}")
                    return False
        return False

    def predict_relative_depth(
        self,
        image: Union[Image.Image, np.ndarray, "torch.Tensor"],
    ) -> np.ndarray:
        """
        Execute monocular depth estimation on optical imagery.
        Returns a 2D float32 array normalized to [0.0, 1.0] (relative heightfield).
        0.0 = lowest relative point, 1.0 = highest relative peak.
        """
        pil_image = self._to_pil_image(image)
        relative_height = self.estimator.estimate(pil_image)
        return relative_height.astype(np.float32)

    def predict_metric_elevation(
        self,
        relative_depth: np.ndarray,
        reference_dem: Optional[np.ndarray] = None,
        valid_mask: Optional[np.ndarray] = None,
        scale: Optional[float] = None,
        offset: Optional[float] = None,
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Calibrate dimensionless relative depth into metric elevation in meters.
        
        Two execution protocols:
        1. Frozen Global Calibration: scale and offset provided. Applies h = a * d_rel + b
           without referencing ground-truth DSM.
        2. Per-image Least Squares (Oracle Upper Bound): fits affine against reference DEM
           exclusively on valid pixels.
        """
        if scale is not None and offset is not None:
            calibrated_elevation = (float(scale) * relative_depth + float(offset)).astype(np.float32)
            calibration_stats = {
                "protocol": "frozen_global_affine",
                "scale": float(scale),
                "offset_meters": float(offset),
            }
            if reference_dem is not None:
                mask = (valid_mask.squeeze().astype(bool) if valid_mask is not None
                        else (np.isfinite(relative_depth) & np.isfinite(reference_dem)))
                x_samples = relative_depth[mask]
                y_samples = reference_dem[mask]
                if len(x_samples) > 0:
                    err = calibrated_elevation[mask] - y_samples
                    calibration_stats["rmse"] = float(np.sqrt(np.mean(err ** 2)))
                    calibration_stats["mae"] = float(np.mean(np.abs(err)))
                    std_x, std_y = float(np.std(x_samples)), float(np.std(y_samples))
                    calibration_stats["correlation"] = float(np.corrcoef(x_samples, y_samples)[0, 1]) if (std_x > 1e-7 and std_y > 1e-7) else 1.0
                    calibration_stats["valid_samples"] = int(np.count_nonzero(mask))
            return calibrated_elevation, calibration_stats

        # Oracle Upper Bound (per-image fit)
        if reference_dem is None:
            raise ValueError("reference_dem must be supplied when scale and offset are not precomputed.")

        if valid_mask is not None:
            mask = valid_mask.squeeze().astype(bool)
            x_samples = relative_depth[mask]
            y_samples = reference_dem[mask]
        else:
            mask = np.isfinite(relative_depth) & np.isfinite(reference_dem)
            x_samples = relative_depth[mask]
            y_samples = reference_dem[mask]

        scale_fit, offset_fit, rmse, mae, corr = fit_linear_scale_offset(x_samples, y_samples)
        calibrated_elevation = (scale_fit * relative_depth + offset_fit).astype(np.float32)

        calibration_stats = {
            "protocol": "oracle_per_image",
            "scale": scale_fit,
            "offset_meters": offset_fit,
            "rmse": rmse,
            "mae": mae,
            "correlation": corr,
            "valid_samples": int(np.count_nonzero(mask)),
        }

        return calibrated_elevation, calibration_stats

    @staticmethod
    def _to_pil_image(image: Union[Image.Image, np.ndarray, "torch.Tensor"]) -> Image.Image:
        """Convert tensor/array/PIL input to a PIL RGB image."""
        if isinstance(image, Image.Image):
            return image.convert("RGB")

        if torch is not None and isinstance(image, torch.Tensor):
            image = image.detach().cpu().numpy()
        if not isinstance(image, np.ndarray):
            raise TypeError(f"Unsupported image type: {type(image)}")

        arr = np.asarray(image)
        if arr.ndim == 4:  # (B, C, H, W) -> (C, H, W)
            arr = arr[0]
        if arr.ndim == 3 and arr.shape[0] in (1, 3):  # channels-first -> channels-last
            arr = np.transpose(arr, (1, 2, 0))
        if arr.ndim == 3 and arr.shape[-1] == 1:  # grayscale -> RGB
            arr = np.repeat(arr, 3, axis=-1)

        if arr.dtype not in (np.uint8,):
            arr_min, arr_max = float(arr.min()), float(arr.max())
            if 0.0 <= arr_min and arr_max <= 1.0:
                arr = arr * 255.0  # already-normalized float range
            elif arr_max > arr_min:
                arr = (arr - arr_min) / (arr_max - arr_min) * 255.0
            else:
                arr = np.zeros_like(arr)
            arr = arr.astype(np.uint8)

        if arr.ndim == 2:
            return Image.fromarray(arr, mode="L").convert("RGB")
        return Image.fromarray(arr, mode="RGB")
