import logging
from typing import Optional, Tuple, Union
import numpy as np
from PIL import Image

from ml.config import (
    IMAGENET_MEAN,
    IMAGENET_STD,
    MAX_PLAUSIBLE_ELEVATION,
    MIN_PLAUSIBLE_ELEVATION,
)

logger = logging.getLogger("depthwizard.ml.preprocessing")


def normalize_image(
    image: np.ndarray,
    mean: Tuple[float, float, float] = IMAGENET_MEAN,
    std: Tuple[float, float, float] = IMAGENET_STD,
) -> np.ndarray:
    """
    Normalize an RGB image array for Depth Anything V2 / PyTorch vision backbones.
    Input: np.ndarray of shape (H, W, 3), dtype uint8 or float.
    Output: np.ndarray of shape (H, W, 3), dtype float32 normalized by (x - mean) / std.
    """
    arr = image.astype(np.float32)
    if arr.max() > 1.0:
        arr /= 255.0

    mean_arr = np.array(mean, dtype=np.float32).reshape(1, 1, 3)
    std_arr = np.array(std, dtype=np.float32).reshape(1, 1, 3)
    return (arr - mean_arr) / std_arr


def create_dem_valid_mask(
    dem: np.ndarray,
    nodata_value: Optional[float] = None,
    min_valid: float = MIN_PLAUSIBLE_ELEVATION,
    max_valid: float = MAX_PLAUSIBLE_ELEVATION,
) -> np.ndarray:
    """
    Construct a boolean mask indicating valid ground-truth elevation pixels.
    Returns 2D bool array where True represents genuine ground-truth elevation.
    Filters out:
      - NaN and Inf values
      - Explicit GeoTIFF NoData values (e.g., -9999, -32767)
      - Unphysical extreme values outside [min_valid, max_valid]
    """
    dem_2d = dem.squeeze()
    valid = np.isfinite(dem_2d)

    if nodata_value is not None and np.isfinite(nodata_value):
        # Use relative tolerance for float comparisons
        valid &= ~np.isclose(dem_2d, nodata_value, atol=1e-3, equal_nan=False)

    valid &= (dem_2d >= min_valid) & (dem_2d <= max_valid)
    return valid.astype(bool)


def align_dem_to_image(
    dem: np.ndarray,
    target_shape: Tuple[int, int],
    resampling_mode: str = "bilinear",
) -> np.ndarray:
    """
    Align and resample a 2D DEM raster to match the optical image spatial dimensions (H, W).
    Preserves exact floating-point elevation values without uint8 clipping.
    """
    dem_2d = dem.squeeze()
    h, w = target_shape

    if dem_2d.shape == (h, w):
        return dem_2d.astype(np.float32)

    # Use PIL float32 resampling
    pil_mode = Image.Resampling.BILINEAR if resampling_mode == "bilinear" else Image.Resampling.NEAREST
    img = Image.fromarray(dem_2d.astype(np.float32), mode="F")
    resampled = img.resize((w, h), resample=pil_mode)
    return np.asarray(resampled, dtype=np.float32)


def prepare_image_tensor(
    image: Union[Image.Image, np.ndarray],
    target_size: Optional[Tuple[int, int]] = None,
    normalize: bool = True,
):
    """
    Convert a PIL Image or numpy array to a PyTorch FloatTensor of shape (3, H, W).
    """
    import torch

    if isinstance(image, Image.Image):
        rgb_img = image.convert("RGB")
        if target_size is not None:
            # PIL resize expects (width, height)
            w, h = target_size[1], target_size[0]
            rgb_img = rgb_img.resize((w, h), resample=Image.Resampling.BILINEAR)
        arr = np.asarray(rgb_img, dtype=np.float32) / 255.0
    else:
        arr = image.astype(np.float32)
        if arr.max() > 1.0:
            arr /= 255.0
        if target_size is not None:
            pil_img = Image.fromarray((arr * 255.0).astype(np.uint8), mode="RGB")
            w, h = target_size[1], target_size[0]
            arr = np.asarray(pil_img.resize((w, h), resample=Image.Resampling.BILINEAR), dtype=np.float32) / 255.0

    if normalize:
        mean_arr = np.array(IMAGENET_MEAN, dtype=np.float32).reshape(1, 1, 3)
        std_arr = np.array(IMAGENET_STD, dtype=np.float32).reshape(1, 1, 3)
        arr = (arr - mean_arr) / std_arr

    # Transpose (H, W, 3) -> (3, H, W)
    arr_chw = np.transpose(arr, (2, 0, 1))
    return torch.from_numpy(arr_chw).float()


def prepare_dem_tensor(
    dem: np.ndarray,
    target_shape: Optional[Tuple[int, int]] = None,
):
    """
    Convert a 2D DEM array to a PyTorch FloatTensor of shape (1, H, W).
    """
    import torch

    dem_2d = dem.squeeze()
    if target_shape is not None:
        dem_2d = align_dem_to_image(dem_2d, target_shape)

    return torch.from_numpy(dem_2d.astype(np.float32)).unsqueeze(0).float()


def prepare_mask_tensor(
    mask: np.ndarray,
    target_shape: Optional[Tuple[int, int]] = None,
):
    """
    Convert a boolean 2D mask to a PyTorch BoolTensor of shape (1, H, W).
    """
    import torch

    mask_2d = mask.squeeze().astype(bool)
    if target_shape is not None and mask_2d.shape != target_shape:
        pil_mask = Image.fromarray(mask_2d.astype(np.uint8) * 255, mode="L")
        w, h = target_shape[1], target_shape[0]
        resampled = pil_mask.resize((w, h), resample=Image.Resampling.NEAREST)
        mask_2d = (np.asarray(resampled) > 127)

    return torch.from_numpy(mask_2d).unsqueeze(0).bool()
