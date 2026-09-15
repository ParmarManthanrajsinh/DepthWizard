import logging
import numpy as np
from typing import Dict, Any, Tuple
from scipy.ndimage import median_filter, gaussian_filter

logger = logging.getLogger("depthwizard.pipeline.ex04a")

EX04A_CONFIG = {
    "depth_clip_low": 2.0,
    "depth_clip_high": 98.0,
    "height_scale": 0.8,
    "vertical_exaggeration": 1.0,
    "height_gamma": 0.85,
    "median_kernel": 5,
    "smoothing_strength": 1.5,
    "max_local_gradient": 3.0,
    "artifact_filter": True,
}

def apply_ex04a_conditioning(
    depth_map: np.ndarray,
    config: Dict[str, Any] = None
) -> Tuple[np.ndarray, Dict[str, float]]:
    """
    Robust terrain geometry stabilization (Experiment 04A).
    Converts raw monocular depth map to a stable height map.
    """
    if config is None:
        config = EX04A_CONFIG

    stats = {}
    
    # 1. Handle NaNs/Infs
    h_map = np.copy(depth_map).astype(np.float32)
    h_map = np.nan_to_num(
        h_map, 
        nan=float(np.nanmedian(depth_map)), 
        posinf=float(np.nanmax(depth_map[depth_map != np.inf])), 
        neginf=float(np.nanmin(depth_map[depth_map != -np.inf]))
    )
    
    if h_map.size == 0 or np.all(h_map == h_map[0, 0]):
        # constant depth or empty
        return h_map, stats
        
    stats['raw_depth_min'] = float(np.min(h_map))
    stats['raw_depth_max'] = float(np.max(h_map))
    stats['raw_depth_mean'] = float(np.mean(h_map))
    stats['raw_depth_std'] = float(np.std(h_map))
    
    gy, gx = np.gradient(h_map)
    grad_mag = np.sqrt(gx**2 + gy**2)
    stats['max_gradient_before'] = float(np.max(grad_mag))
    stats['p95_gradient_before'] = float(np.percentile(grad_mag, 95))
    stats['p99_gradient_before'] = float(np.percentile(grad_mag, 99))
    
    # 2. Outlier Handling (Percentile Clipping)
    low_p = config.get("depth_clip_low", 2.0)
    high_p = config.get("depth_clip_high", 98.0)
    
    clip_min = float(np.percentile(h_map, low_p))
    clip_max = float(np.percentile(h_map, high_p))
    
    clipped_pixels = np.sum((h_map < clip_min) | (h_map > clip_max))
    stats['pct_pixels_clipped'] = float(clipped_pixels / h_map.size * 100.0)
    
    h_map = np.clip(h_map, clip_min, clip_max)
    
    stats['clipped_depth_min'] = float(np.min(h_map))
    stats['clipped_depth_max'] = float(np.max(h_map))
    
    # 3. Depth Normalization & Height Compression
    span = clip_max - clip_min
    if span > 1e-6:
        h_norm = (h_map - clip_min) / span
    else:
        h_norm = np.zeros_like(h_map)
        
    gamma = config.get("height_gamma", 1.0)
    h_norm = np.power(h_norm, gamma)
    
    target_range = span * config.get("height_scale", 1.0) * config.get("vertical_exaggeration", 1.0)
    h_calib = h_norm * target_range + clip_min
    
    # 4. Building / Object Artifact Mitigation
    if config.get("artifact_filter", True):
        k = config.get("median_kernel", 5)
        if k > 0:
            h_calib = median_filter(h_calib, size=k)
            
    # 5. Slope / Gradient Limiting
    max_grad = config.get("max_local_gradient", 3.0)
    if max_grad > 0:
        for _ in range(2):
            gy, gx = np.gradient(h_calib)
            grad_mag = np.sqrt(gx**2 + gy**2)
            mask = grad_mag > max_grad
            if not np.any(mask):
                break
            # Replace extreme slopes with local median
            h_calib[mask] = median_filter(h_calib, size=7)[mask]

    # 6. Edge-aware smoothing
    sigma = config.get("smoothing_strength", 1.0)
    if sigma > 0:
        h_calib = gaussian_filter(h_calib, sigma=sigma)
        
    # Calculate final stats
    stats['conditioned_depth_min'] = float(np.min(h_calib))
    stats['conditioned_depth_max'] = float(np.max(h_calib))
    stats['conditioned_depth_mean'] = float(np.mean(h_calib))
    stats['conditioned_depth_std'] = float(np.std(h_calib))
    
    gy, gx = np.gradient(h_calib)
    grad_mag = np.sqrt(gx**2 + gy**2)
    stats['max_gradient_after'] = float(np.max(grad_mag))
    stats['p95_gradient_after'] = float(np.percentile(grad_mag, 95))
    stats['p99_gradient_after'] = float(np.percentile(grad_mag, 99))
    
    modified_pixels = np.sum(np.abs(h_calib - depth_map) > 1e-4)
    stats['pct_height_modified'] = float(modified_pixels / h_map.size * 100.0)
    
    # Approximate mesh stats (assumes typical 1-to-1 triangulation or similar)
    stats['mesh_vertex_count'] = h_calib.size
    stats['mesh_triangle_count'] = (h_calib.shape[0]-1) * (h_calib.shape[1]-1) * 2
    
    return h_calib.astype(np.float32), stats
