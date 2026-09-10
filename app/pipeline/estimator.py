from abc import ABC, abstractmethod
import logging
from typing import Optional
import numpy as np
from PIL import Image

from app.config import DEPTH_MODEL_NAME, DEVICE, USE_MOCK_MODEL

logger = logging.getLogger("depthwizard.pipeline.estimator")


class BaseDepthEstimator(ABC):
    """Base interface for all monocular depth estimators."""

    @abstractmethod
    def estimate(self, image: Image.Image) -> np.ndarray:
        """
        Produce a relative depth/elevation map from a PIL Image.
        Returns a 2D float32 numpy array normalized to [0.0, 1.0].
        """
        pass


class MockDepthEstimator(BaseDepthEstimator):
    """
    High-fidelity synthetic/heuristic depth estimator for development.
    Extracts pseudo-elevation from image luminance combined with multi-scale
    terrain gradient synthesis. Ensures any team member can test the full
    monorepo flow offline without downloading multi-gigabyte models or needing GPU.
    """

    def estimate(self, image: Image.Image) -> np.ndarray:
        logger.info("Running MockDepthEstimator (development mode)...")
        # Convert to grayscale
        gray = image.convert("L")
        w, h = gray.size
        arr = np.asarray(gray, dtype=np.float32) / 255.0

        # Multi-scale synthetic relief: blend image luminance with synthetic topography
        y = np.linspace(-1.0, 1.0, h, dtype=np.float32)[:, None]
        x = np.linspace(-1.0, 1.0, w, dtype=np.float32)[None, :]
        r = np.sqrt(x * x + y * y)

        # Topographic wave structure
        terrain_macro = 0.5 * (np.cos(x * 3.14 * 2.0) * np.sin(y * 3.14 * 2.0) + 1.0)
        terrain_ridge = 0.3 * np.exp(-4.0 * (r - 0.4) ** 2)
        terrain_micro = 0.2 * arr

        heightmap = terrain_macro + terrain_ridge + terrain_micro
        
        # Normalize strictly to [0.0, 1.0]
        h_min, h_max = float(heightmap.min()), float(heightmap.max())
        if h_max > h_min:
            heightmap = (heightmap - h_min) / (h_max - h_min)
        else:
            heightmap = np.zeros_like(heightmap)

        return heightmap.astype(np.float32)


class DepthAnythingV2Estimator(BaseDepthEstimator):
    """
    Monocular depth estimation using Depth Anything V2 via HuggingFace transformers.
    Produces state-of-the-art relative depth maps for arbitrary optical scenes.
    """

    def __init__(self, model_name: str = DEPTH_MODEL_NAME, device: str = DEVICE):
        self.model_name = model_name
        self.device = device
        self._model = None
        self._processor = None
        self._initialized = False

    def _load(self) -> None:
        if self._initialized:
            return

        try:
            import torch
            from transformers import AutoImageProcessor, AutoModelForDepthEstimation

            logger.info(f"Loading Depth Anything V2 from '{self.model_name}' on {self.device}...")
            self._processor = AutoImageProcessor.from_pretrained(self.model_name)
            self._model = AutoModelForDepthEstimation.from_pretrained(self.model_name)
            self._model.to(self.device)
            self._model.eval()
            self._initialized = True
            logger.info("Depth Anything V2 loaded successfully.")
        except Exception as e:
            logger.warning(
                f"Could not load HuggingFace model '{self.model_name}': {e}. "
                "Falling back to MockDepthEstimator."
            )
            self._initialized = False

    def estimate(self, image: Image.Image) -> np.ndarray:
        self._load()
        if not self._initialized or self._model is None or self._processor is None:
            return MockDepthEstimator().estimate(image)

        import torch
        inputs = self._processor(images=image, return_tensors="pt").to(self.device)
        with torch.no_grad():
            outputs = self._model(**inputs)
            predicted_depth = outputs.predicted_depth

        # Interpolate back to original image resolution
        w, h = image.size
        prediction = torch.nn.functional.interpolate(
            predicted_depth.unsqueeze(1),
            size=(h, w),
            mode="bicubic",
            align_corners=False,
        ).squeeze().cpu().numpy()

        # In depth models, smaller depth value = closer / higher elevation
        # Invert to turn depth into heightmap: 0 = valley, 1 = peak
        d_min, d_max = float(prediction.min()), float(prediction.max())
        if d_max > d_min:
            heightmap = 1.0 - ((prediction - d_min) / (d_max - d_min))
        else:
            heightmap = np.zeros_like(prediction)

        return heightmap.astype(np.float32)


def get_depth_estimator(force_mock: Optional[bool] = None) -> BaseDepthEstimator:
    """Factory providing the active depth estimator."""
    use_mock = force_mock if force_mock is not None else USE_MOCK_MODEL
    if use_mock:
        return MockDepthEstimator()

    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
        return DepthAnythingV2Estimator()
    except ImportError:
        logger.info("torch/transformers not found in environment. Using MockDepthEstimator.")
        return MockDepthEstimator()
