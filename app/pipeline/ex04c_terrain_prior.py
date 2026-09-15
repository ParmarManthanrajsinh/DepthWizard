"""
Experiment 04C — Multi-Scale Terrain Prior + Robust Height Fusion

Extracts a low-frequency terrain prior from the monocular depth prediction
and fuses it with the original signal so that large-scale terrain structure
(hills, valleys, ridges) is preserved while high-frequency artifacts
(building spikes, tree peaks, shadow discontinuities) are suppressed.

Designed to slot BEFORE EX04A conditioning:

    depth -> EX04C (terrain prior fusion) -> EX04A (geometry stabilisation) -> mesh

Does NOT replace EX04A.  When disabled, the pipeline is identical to EX04A-only.
"""

import logging
import time
from typing import Any, Dict, Optional, Tuple

import numpy as np
from scipy.ndimage import gaussian_filter, median_filter

logger = logging.getLogger("depthwizard.pipeline.ex04c")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

EX04C_CONFIG: Dict[str, Any] = {
    # Master switch — production default is OFF
    "enabled": False,

    # --- Multi-scale decomposition ---
    # Sigma values for the Gaussian pyramid (in pixels).
    # medium captures neighbourhood structure; coarse captures broad terrain.
    "sigma_medium": 8.0,
    "sigma_coarse": 24.0,

    # --- Fusion ---
    # Base weight for the low-frequency terrain prior [0..1].
    # 0 = use original signal entirely; 1 = use coarse prior entirely.
    "fusion_alpha": 0.35,

    # Detail preservation weight — controls how much of the band-passed
    # medium-frequency detail (medium − coarse) is added back.
    "detail_weight": 0.25,

    # --- Adaptive weighting ---
    # When True, fusion_alpha is modulated per-pixel: extreme local gradients
    # get *more* prior influence; smooth regions keep the original signal.
    "adaptive": True,

    # Gradient percentile above which a pixel is considered "extreme" and
    # receives full prior influence.
    "adaptive_gradient_pct": 90.0,

    # --- Safety ---
    # Preserve the global mean of the original signal after fusion so that
    # SRTM/AGL calibration is not biased.
    "preserve_mean": True,
}


# ---------------------------------------------------------------------------
# Core algorithm
# ---------------------------------------------------------------------------

def _multi_scale_decompose(
    signal: np.ndarray,
    sigma_medium: float,
    sigma_coarse: float,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Decompose *signal* into three spatial-frequency bands.

    Returns (fine_detail, medium_detail, coarse_terrain).
    fine_detail + medium_detail + coarse_terrain ≈ signal
    """
    coarse = gaussian_filter(signal, sigma=sigma_coarse)
    medium = gaussian_filter(signal, sigma=sigma_medium)
    medium_band = medium - coarse        # medium-frequency band
    fine_band = signal - medium           # high-frequency band
    return fine_band, medium_band, coarse


def _adaptive_alpha(
    signal: np.ndarray,
    base_alpha: float,
    gradient_pct: float,
) -> np.ndarray:
    """Compute per-pixel fusion weight: higher where gradients are extreme."""
    gy, gx = np.gradient(signal)
    grad_mag = np.sqrt(gx ** 2 + gy ** 2)

    # Threshold: gradients above this percentile get full prior weight
    thresh = float(np.percentile(grad_mag, gradient_pct))
    if thresh < 1e-8:
        return np.full_like(signal, base_alpha)

    # Smoothly ramp alpha from base_alpha (calm) to 1.0 (extreme)
    ratio = np.clip(grad_mag / thresh, 0.0, 1.0)
    alpha_map = base_alpha + (1.0 - base_alpha) * ratio

    # Light spatial smoothing so weight map is not itself noisy
    alpha_map = gaussian_filter(alpha_map, sigma=3.0)
    return alpha_map.astype(np.float32)


def apply_ex04c_terrain_prior(
    depth_map: np.ndarray,
    config: Optional[Dict[str, Any]] = None,
) -> Tuple[np.ndarray, Dict[str, float]]:
    """Apply multi-scale terrain prior fusion.

    Parameters
    ----------
    depth_map : float32 2-D array of predicted AGL heights
    config    : optional overrides for EX04C_CONFIG

    Returns
    -------
    fused : float32 2-D height map
    stats : diagnostic statistics
    """
    cfg = {**EX04C_CONFIG, **(config or {})}
    t0 = time.time()
    stats: Dict[str, float] = {}

    if not cfg.get("enabled", False):
        stats["ex04c_enabled"] = 0.0
        stats["ex04c_time_s"] = 0.0
        return depth_map.copy().astype(np.float32), stats

    # --- Sanitise input ---
    dm = np.copy(depth_map).astype(np.float32)
    dm = np.nan_to_num(dm, nan=0.0, posinf=0.0, neginf=0.0)
    original_mean = float(np.mean(dm))

    # --- Decompose ---
    sigma_m = cfg["sigma_medium"]
    sigma_c = cfg["sigma_coarse"]
    fine, medium_band, coarse = _multi_scale_decompose(dm, sigma_m, sigma_c)

    stats["coarse_min"] = float(np.min(coarse))
    stats["coarse_max"] = float(np.max(coarse))
    stats["fine_std"] = float(np.std(fine))
    stats["medium_std"] = float(np.std(medium_band))

    # --- Compute fusion weight ---
    base_alpha = cfg["fusion_alpha"]
    if cfg.get("adaptive", False):
        alpha = _adaptive_alpha(dm, base_alpha, cfg["adaptive_gradient_pct"])
        stats["alpha_mean"] = float(np.mean(alpha))
        stats["alpha_max"] = float(np.max(alpha))
    else:
        alpha = base_alpha
        stats["alpha_mean"] = base_alpha
        stats["alpha_max"] = base_alpha

    # --- Fuse ---
    # terrain_prior = coarse + fraction of medium detail
    detail_w = cfg["detail_weight"]
    terrain_prior = coarse + detail_w * medium_band

    # Blend: fused = alpha * terrain_prior + (1 - alpha) * original
    fused = alpha * terrain_prior + (1.0 - alpha) * dm

    # --- Preserve physical mean ---
    if cfg.get("preserve_mean", True):
        fused_mean = float(np.mean(fused))
        if abs(fused_mean) > 1e-8:
            fused = fused + (original_mean - fused_mean)

    elapsed = time.time() - t0
    stats["ex04c_enabled"] = 1.0
    stats["ex04c_time_s"] = elapsed
    stats["fused_min"] = float(np.min(fused))
    stats["fused_max"] = float(np.max(fused))
    stats["fused_mean"] = float(np.mean(fused))
    stats["fused_std"] = float(np.std(fused))
    stats["mean_shift"] = abs(float(np.mean(fused)) - original_mean)

    logger.info(
        f"Ex04C: sigma_m={sigma_m}, sigma_c={sigma_c}, "
        f"alpha_mean={stats['alpha_mean']:.3f}, "
        f"fine_std={stats['fine_std']:.3f}, "
        f"elapsed={elapsed:.3f}s"
    )

    return fused.astype(np.float32), stats
