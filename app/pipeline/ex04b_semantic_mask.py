"""
Experiment 04B — Semantic / Object Exclusion for Terrain Reconstruction

Derives terrain-only height maps from monocular depth predictions by detecting
above-ground objects (buildings, trees, vehicles) using local height contrast
in the predicted depth itself, then reconstructing the underlying terrain
surface via surrounding-terrain interpolation.

No external segmentation model is required. Works purely from the predicted
AGL depth map using morphological and statistical analysis.
"""

import logging
import time
from typing import Any, Dict, Optional, Tuple

import numpy as np
from scipy.ndimage import (
    binary_dilation,
    binary_erosion,
    gaussian_filter,
    label as ndimage_label,
    median_filter,
    uniform_filter,
)

logger = logging.getLogger("depthwizard.pipeline.ex04b")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

EX04B_CONFIG = {
    # --- Object detection thresholds ---
    # Minimum AGL height (meters) for a pixel to be considered an above-ground
    # object candidate. Ground-level terrain is typically < 2m AGL.
    "object_height_threshold": 2.0,

    # Local contrast: an object pixel must exceed the local background by at
    # least this many meters (avoids flagging gentle hills as objects).
    "local_contrast_threshold": 1.5,

    # Size of the local background window (pixels) for computing the local
    # ground-level reference.  Must be large enough that a building does not
    # dominate its own background estimate.
    "local_bg_window": 31,

    # Minimum connected-component area (pixels) to keep as a detected object.
    # Small isolated noise patches below this are discarded.
    "min_object_area": 25,

    # --- Mask cleanup ---
    # Morphological dilation iterations applied to the raw object mask so that
    # object edges (walls, roof overhangs) are covered.
    "mask_dilation_iterations": 2,

    # --- Terrain interpolation ---
    # Method for reconstructing the terrain surface under detected objects.
    # Options: "local_median", "gaussian_fill"
    "terrain_fill_method": "local_median",

    # Kernel size for the local median terrain estimate used to fill object
    # regions.  Should be significantly larger than typical building footprints.
    "terrain_fill_kernel": 21,

    # Gaussian sigma for the final blending pass that smooths the boundary
    # between real terrain and interpolated terrain under objects.
    "boundary_blend_sigma": 3.0,

    # --- Safety ---
    # Enable/disable EX04B.  When False, the module returns the input unchanged.
    "enabled": True,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_object_mask(
    depth_map: np.ndarray,
    config: Optional[Dict[str, Any]] = None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, Dict[str, float]]:
    """Produce terrain / object / unknown masks from predicted AGL depth.

    Returns
    -------
    terrain_mask : bool ndarray  — True where pixel is classified as terrain
    object_mask  : bool ndarray  — True where pixel is classified as above-ground object
    unknown_mask : bool ndarray  — True where classification is uncertain
    stats        : dict          — diagnostic statistics
    """
    cfg = {**EX04B_CONFIG, **(config or {})}
    h, w = depth_map.shape
    stats: Dict[str, float] = {}

    # Sanitize input
    dm = np.copy(depth_map).astype(np.float32)
    dm = np.nan_to_num(dm, nan=0.0, posinf=0.0, neginf=0.0)

    # Step 1 — Compute local background (low-frequency terrain estimate)
    bg_win = cfg["local_bg_window"]
    # Use a large percentile-based local minimum as terrain estimate.
    # uniform_filter on a rank-order proxy is expensive; instead use a large
    # median (approximates ground level in mixed urban scenes).
    local_bg = median_filter(dm, size=bg_win)

    # Step 2 — Local contrast: how much does each pixel exceed local background?
    local_contrast = dm - local_bg

    # Step 3 — Object candidate mask
    abs_thresh = cfg["object_height_threshold"]
    contrast_thresh = cfg["local_contrast_threshold"]
    raw_obj = (dm > abs_thresh) & (local_contrast > contrast_thresh)

    stats["raw_object_pixels"] = float(raw_obj.sum())
    stats["raw_object_pct"] = float(raw_obj.sum() / raw_obj.size * 100.0)

    # Step 4 — Remove small connected components (noise)
    min_area = cfg["min_object_area"]
    labeled_array, num_features = ndimage_label(raw_obj)
    cleaned_obj = np.zeros_like(raw_obj)
    for i in range(1, num_features + 1):
        component = labeled_array == i
        if component.sum() >= min_area:
            cleaned_obj |= component

    # Step 5 — Morphological dilation to cover edges
    dil_iter = cfg["mask_dilation_iterations"]
    if dil_iter > 0:
        struct = np.ones((3, 3), dtype=bool)
        object_mask = binary_dilation(cleaned_obj, structure=struct, iterations=dil_iter)
    else:
        object_mask = cleaned_obj

    stats["final_object_pixels"] = float(object_mask.sum())
    stats["final_object_pct"] = float(object_mask.sum() / object_mask.size * 100.0)
    stats["num_object_regions"] = float(num_features)

    # Terrain and unknown masks
    terrain_mask = ~object_mask
    unknown_mask = np.zeros_like(object_mask)  # deterministic — no unknowns in this method

    return terrain_mask.astype(bool), object_mask.astype(bool), unknown_mask.astype(bool), stats


def reconstruct_terrain_under_objects(
    depth_map: np.ndarray,
    object_mask: np.ndarray,
    config: Optional[Dict[str, Any]] = None,
) -> Tuple[np.ndarray, Dict[str, float]]:
    """Replace above-ground object heights with estimated underlying terrain.

    The terrain under objects is estimated from surrounding terrain-only pixels
    so that the reconstructed surface is continuous (a building on a hill keeps
    the hill surface underneath).

    Parameters
    ----------
    depth_map   : float32 2-D array of predicted AGL heights
    object_mask : bool 2-D array (True = above-ground object)
    config      : optional overrides for EX04B_CONFIG

    Returns
    -------
    terrain_depth : float32 2-D array with objects replaced by terrain estimate
    stats         : diagnostic statistics
    """
    cfg = {**EX04B_CONFIG, **(config or {})}
    stats: Dict[str, float] = {}

    dm = np.copy(depth_map).astype(np.float32)
    dm = np.nan_to_num(dm, nan=0.0, posinf=0.0, neginf=0.0)

    terrain_mask = ~object_mask
    obj_count = int(object_mask.sum())

    if obj_count == 0:
        stats["objects_filled"] = 0
        stats["pct_filled"] = 0.0
        return dm, stats

    # Build terrain-only surface estimate
    method = cfg["terrain_fill_method"]
    fill_k = cfg["terrain_fill_kernel"]

    if method == "local_median":
        # Set object pixels to NaN, then fill with large-kernel median of terrain
        terrain_only = dm.copy()
        terrain_only[object_mask] = np.nan

        # We cannot pass NaN to median_filter directly. Instead, replace NaN with
        # the global terrain median first, run median filter, then blend.
        terrain_median_global = float(np.nanmedian(terrain_only))
        terrain_only_filled = np.where(np.isnan(terrain_only), terrain_median_global, terrain_only)
        terrain_surface = median_filter(terrain_only_filled, size=fill_k)

    elif method == "gaussian_fill":
        terrain_only = dm.copy()
        terrain_only[object_mask] = 0.0
        weight = (~object_mask).astype(np.float32)
        # Weighted Gaussian interpolation (Nadaraya-Watson)
        sigma = fill_k / 3.0
        smoothed_vals = gaussian_filter(terrain_only * weight, sigma=sigma)
        smoothed_weight = gaussian_filter(weight, sigma=sigma)
        smoothed_weight = np.maximum(smoothed_weight, 1e-8)
        terrain_surface = smoothed_vals / smoothed_weight
    else:
        # Fallback — simple global median fill
        terrain_surface = np.full_like(dm, float(np.nanmedian(dm[terrain_mask])))

    # Replace object pixels with estimated terrain surface
    result = dm.copy()
    result[object_mask] = terrain_surface[object_mask]

    # Smooth the boundary between real terrain and interpolated terrain
    blend_sigma = cfg["boundary_blend_sigma"]
    if blend_sigma > 0:
        # Only blend in a narrow band around objects to avoid disturbing real terrain
        boundary_band = binary_dilation(object_mask, iterations=3) & ~binary_erosion(object_mask, iterations=1)
        blended = gaussian_filter(result, sigma=blend_sigma)
        result[boundary_band] = blended[boundary_band]

    stats["objects_filled"] = obj_count
    stats["pct_filled"] = float(obj_count / dm.size * 100.0)

    # Measure elevation variance reduction in object regions
    stats["object_region_var_before"] = float(np.var(dm[object_mask]))
    stats["object_region_var_after"] = float(np.var(result[object_mask]))
    stats["terrain_region_var"] = float(np.var(dm[terrain_mask]))

    return result.astype(np.float32), stats


def apply_ex04b_conditioning(
    depth_map: np.ndarray,
    config: Optional[Dict[str, Any]] = None,
) -> Tuple[np.ndarray, Dict[str, float]]:
    """Full EX04B pipeline: detect objects → reconstruct terrain → return.

    Designed to slot into the main pipeline BEFORE EX04A conditioning:

        depth → EX04B (object exclusion) → EX04A (geometry stabilization) → mesh

    Parameters
    ----------
    depth_map : float32 2-D predicted AGL height map
    config    : optional overrides for EX04B_CONFIG

    Returns
    -------
    conditioned : float32 2-D height map with objects replaced by terrain
    stats       : combined diagnostic statistics
    """
    cfg = {**EX04B_CONFIG, **(config or {})}
    t0 = time.time()

    if not cfg.get("enabled", True):
        return depth_map.copy().astype(np.float32), {"ex04b_enabled": 0.0, "ex04b_time_s": 0.0}

    # Phase 1 — Object detection
    terrain_mask, object_mask, unknown_mask, mask_stats = generate_object_mask(depth_map, cfg)

    # Phase 2 — Terrain reconstruction
    result, fill_stats = reconstruct_terrain_under_objects(depth_map, object_mask, cfg)

    elapsed = time.time() - t0

    # Merge stats
    all_stats: Dict[str, float] = {
        "ex04b_enabled": 1.0,
        "ex04b_time_s": elapsed,
        **mask_stats,
        **fill_stats,
    }

    logger.info(
        f"Ex04B: detected {mask_stats['final_object_pct']:.1f}% object pixels "
        f"({int(mask_stats['num_object_regions'])} regions), "
        f"filled {fill_stats['pct_filled']:.1f}% in {elapsed:.3f}s"
    )

    return result, all_stats
