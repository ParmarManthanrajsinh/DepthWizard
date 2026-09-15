from abc import ABC, abstractmethod
import logging
from typing import Optional
import numpy as np
from PIL import Image

from app.config import DEPTH_MODEL_NAME, DEVICE, USE_MOCK_MODEL, BASE_DIR

logger = logging.getLogger("depthwizard.pipeline.estimator")


class BaseDepthEstimator(ABC):
    """Base interface for all monocular depth estimators."""

    @abstractmethod
    def estimate(self, image: Image.Image) -> np.ndarray:
        """
        Produce a depth/elevation map from a PIL Image.
        Returns a 2D float32 numpy array.
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

        # Depth Anything V2 outputs disparity / relative inverse depth where
        # objects closer to the top-down optical sensor (rooftops, trees, elevated terrain)
        # naturally produce LARGER values, and lower ground / valleys produce SMALLER values.
        # Normalize directly to [0.0, 1.0] relative height: 0.0 = low/ground, 1.0 = peak.
        d_min, d_max = float(prediction.min()), float(prediction.max())
        if d_max > d_min:
            heightmap = (prediction - d_min) / (d_max - d_min)
        else:
            heightmap = np.zeros_like(prediction)

        return heightmap.astype(np.float32)


class DepthWizard03BEstimator(BaseDepthEstimator):
    """
    Monocular metric AGL height estimation using Experiment 03B LoRA configuration.
    Directly returns absolute metric elevations in meters.
    """

    def __init__(self, device: str = DEVICE):
        self.device = device
        self._model = None
        self._initialized = False
        
        # EX05-R1 Migration: Replaced best_gamus_exp03b.pt with checkpoints/exp05_r1/best.pt
        self.checkpoint_path = BASE_DIR / "checkpoints" / "exp05_r1" / "best.pt"
        
        self.imagenet_mean = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(1, 1, 3)
        self.imagenet_std = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(1, 1, 3)

    def _load(self) -> None:
        if self._initialized:
            return

        import torch
        import sys
        
        if str(BASE_DIR) not in sys.path:
            sys.path.insert(0, str(BASE_DIR))
            
        try:
            from ml.lora_model import LoRAMetricDepthAnythingV2
        except ImportError:
            raise RuntimeError("Failed to import LoRAMetricDepthAnythingV2. Check PYTHONPATH.")

        logger.info(f"Loading DepthWizard-05-R1 from '{self.checkpoint_path}' on {self.device}...")
        
        if not self.checkpoint_path.exists():
            raise RuntimeError(f"03B checkpoint missing at: {self.checkpoint_path}")

        try:
            # 1. Base Model
            logger.info("Loading foundation model from 'depth-anything/Depth-Anything-V2-Small-hf'...")
            self._model = LoRAMetricDepthAnythingV2(lora_r=8, lora_alpha=16.0)
            
            # 2. Load Checkpoint
            checkpoint = torch.load(self.checkpoint_path, map_location=self.device, weights_only=False)
            state_dict = checkpoint.get("model_state_dict", checkpoint.get("trainable_state_dict"))
            self._model.load_state_dict(state_dict, strict=False)
            
            # 3. Eval & Device
            self._model.to(self.device)
            self._model.eval()
            self._initialized = True
            
            gpu_name = torch.cuda.get_device_name(0) if torch.device(self.device).type == "cuda" and torch.cuda.is_available() else "CPU"
            epoch = checkpoint.get("epoch", "unknown")
            logger.info(f"DepthWizard-05-R1 (Epoch {epoch}) loaded successfully on {self.device} ({gpu_name}).")
            
        except Exception as e:
            logger.error(f"Failed to load DepthWizard-05-R1 model from {self.checkpoint_path}")
            raise RuntimeError(f"Failed to load DepthWizard-05-R1 model: {e}")

    def estimate(self, image: Image.Image) -> np.ndarray:
        self._load()
        
        import torch
        
        # Image is converted to RGB and values are [0,1].
        w, h = image.size
        rgb_full = np.array(image.convert("RGB"), dtype=np.float32) / 255.0
        
        crop_size = 518
        
        with torch.no_grad():
            if h == 1024 and w == 1024:
                # Use standard four-corner strategy
                corners = [
                    (0, 0),
                    (0, w - crop_size),
                    (h - crop_size, 0),
                    (h - crop_size, w - crop_size),
                ]
                
                patches = []
                for top, left in corners:
                    crop = rgb_full[top : top + crop_size, left : left + crop_size, :]
                    norm_crop = (crop - self.imagenet_mean) / self.imagenet_std
                    tensor_crop = torch.from_numpy(norm_crop.transpose(2, 0, 1)).float()
                    patches.append(tensor_crop)
                    
                batch = torch.stack(patches, dim=0).to(self.device)
                preds = self._model(batch).cpu().numpy()
                
                full_pred = np.zeros((h, w), dtype=np.float32)
                weight_map = np.zeros((h, w), dtype=np.float32)

                for i, (top, left) in enumerate(corners):
                    full_pred[top : top + crop_size, left : left + crop_size] += preds[i]
                    weight_map[top : top + crop_size, left : left + crop_size] += 1.0

                prediction = full_pred / np.maximum(weight_map, 1e-6)
            
            else:
                # For smaller/different dimensions, safely resize or tile
                # Here we just resize the input to crop_size x crop_size, predict, then resize back
                # This avoids breaking dimensions while preserving original output resolution
                # For large arbitrary sizes, a robust tiling would be needed, but simple resize is safest here.
                rgb_resized = np.array(image.convert("RGB").resize((crop_size, crop_size), Image.LANCZOS), dtype=np.float32) / 255.0
                norm_crop = (rgb_resized - self.imagenet_mean) / self.imagenet_std
                tensor_crop = torch.from_numpy(norm_crop.transpose(2, 0, 1)).float()
                
                batch = tensor_crop.unsqueeze(0).to(self.device)
                pred_crop = self._model(batch).squeeze(0).cpu().numpy()
                
                # Resize prediction back to original dimensions
                pred_img = Image.fromarray(pred_crop)
                prediction = np.array(pred_img.resize((w, h), Image.BILINEAR))
                
        # Metric AGL prediction logging
        p_min, p_max = float(np.min(prediction)), float(np.max(prediction))
        p_mean, p_median = float(np.mean(prediction)), float(np.median(prediction))
        p_finite = float(np.isfinite(prediction).sum() / prediction.size * 100.0)
        
        logger.info(f"DepthWizard-03B Prediction: Min={p_min:.2f}m, Max={p_max:.2f}m, "
                    f"Mean={p_mean:.2f}m, Median={p_median:.2f}m, Finite={p_finite:.2f}%")
        
        return prediction.astype(np.float32)

def get_depth_estimator(force_mock: Optional[bool] = None) -> BaseDepthEstimator:
    """Factory providing the active depth estimator."""
    use_mock = force_mock if force_mock is not None else USE_MOCK_MODEL
    if use_mock:
        return MockDepthEstimator()

    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
        return DepthWizard03BEstimator()
    except ImportError:
        logger.info("torch/transformers not found in environment. Using MockDepthEstimator.")
        return MockDepthEstimator()
