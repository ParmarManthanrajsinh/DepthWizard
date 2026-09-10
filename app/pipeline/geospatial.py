import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import numpy as np
from PIL import Image

logger = logging.getLogger("depthwizard.pipeline.geospatial")

# Terrain color ramp: (norm_val, (R, G, B))
COLORMAP_TERRAIN = [
    (0.00, (40, 70, 140)),    # Deep valley / water
    (0.15, (60, 130, 90)),    # Lowland vegetation
    (0.35, (130, 180, 90)),   # Foothills
    (0.60, (200, 180, 110)),  # Highlands
    (0.80, (170, 130, 100)),  # Rocky slopes
    (1.00, (250, 250, 255)),  # Snow / peaks
]


def interpolate_colormap(val: float) -> Tuple[int, int, int]:
    val = float(np.clip(val, 0.0, 1.0))
    for i in range(len(COLORMAP_TERRAIN) - 1):
        v0, c0 = COLORMAP_TERRAIN[i]
        v1, c1 = COLORMAP_TERRAIN[i + 1]
        if v0 <= val <= v1:
            t = (val - v0) / (v1 - v0)
            r = int(c0[0] + t * (c1[0] - c0[0]))
            g = int(c0[1] + t * (c1[1] - c0[1]))
            b = int(c0[2] + t * (c1[2] - c0[2]))
            return (r, g, b)
    return COLORMAP_TERRAIN[-1][1]


def inspect_georeference(filepath: Path) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """
    Check if an image has geospatial referencing metadata (GeoTIFF).
    Returns (is_georeferenced, crs_string, bounds_dict).
    """
    try:
        import rasterio
        with rasterio.open(filepath) as src:
            crs_str = str(src.crs) if src.crs else None
            is_geo = bool(src.crs and src.transform and not src.transform.is_identity)
            bounds = {
                "left": src.bounds.left,
                "bottom": src.bounds.bottom,
                "right": src.bounds.right,
                "top": src.bounds.top,
            } if is_geo else None
            return is_geo, crs_str, bounds
    except ImportError:
        logger.debug("rasterio not installed; inspecting TIFF tags with PIL...")
    except Exception as e:
        logger.debug(f"rasterio open failed: {e}")

    # Fallback to PIL GeoTIFF tag inspection
    try:
        with Image.open(filepath) as img:
            # Check GeoTIFF known tag keys (33550 = ModelPixelScale, 33922 = ModelTiepoint, 34735 = GeoKeyDirectory)
            tag_dict = getattr(img, "tag_v2", {}) or {}
            has_geo_keys = any(k in tag_dict for k in (33550, 33922, 34735))
            if has_geo_keys:
                return True, "EPSG:4326 (GeoTIFF tags detected)", None
    except Exception as e:
        logger.debug(f"PIL tag inspection failed: {e}")

    return False, None, None


def save_dsm_geotiff(
    elevation_map: np.ndarray,
    output_path: Path,
    crs_str: Optional[str] = None,
    bounds: Optional[Dict[str, Any]] = None
) -> Path:
    """
    Write a 2D float32 elevation map to a GeoTIFF.
    Uses rasterio if installed; otherwise saves as 32-bit float TIFF via PIL.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    h, w = elevation_map.shape

    try:
        import rasterio
        from rasterio.transform import from_bounds

        crs = crs_str if crs_str else "EPSG:4326"
        if bounds:
            transform = from_bounds(
                bounds["left"], bounds["bottom"], bounds["right"], bounds["top"], w, h
            )
        else:
            transform = rasterio.transform.Affine(1.0, 0.0, 0.0, 0.0, -1.0, float(h))

        with rasterio.open(
            output_path,
            "w",
            driver="GTiff",
            height=h,
            width=w,
            count=1,
            dtype=elevation_map.dtype,
            crs=crs,
            transform=transform,
        ) as dst:
            dst.write(elevation_map, 1)

        logger.info(f"Saved GeoTIFF DSM via rasterio: {output_path}")
        return output_path
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"rasterio save failed: {e}, using PIL fallback")

    # PIL fallback: save as TIFF image
    img = Image.fromarray(elevation_map.astype(np.float32))
    img.save(output_path, format="TIFF")
    logger.info(f"Saved TIFF DSM via PIL fallback: {output_path}")
    return output_path


def generate_colorized_preview(
    elevation_map: np.ndarray,
    output_path: Path
) -> Path:
    """
    Generate a high-contrast colorized hillshade/elevation preview PNG.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    h_min, h_max = float(elevation_map.min()), float(elevation_map.max())
    if h_max > h_min:
        norm = (elevation_map - h_min) / (h_max - h_min)
    else:
        norm = np.zeros_like(elevation_map)

    h, w = norm.shape
    rgb_arr = np.zeros((h, w, 3), dtype=np.uint8)

    # Fast color lookup table (256 entries)
    lut = np.zeros((256, 3), dtype=np.uint8)
    for i in range(256):
        lut[i] = interpolate_colormap(i / 255.0)

    indices = (norm * 255.0).astype(np.uint8)
    rgb_arr = lut[indices]

    preview_img = Image.fromarray(rgb_arr, mode="RGB")
    preview_img.save(output_path, format="PNG")
    logger.info(f"Generated preview PNG: {output_path}")
    return output_path


def compute_slope_profile(
    elevation_map: np.ndarray,
    cell_size_m: float = 30.0
) -> Dict[str, float]:
    """
    Compute geomorphic slope profile metrics from elevation raster using central differences.
    Returns:
        mean_slope_deg: Mean terrain slope across the scene (degrees)
        max_slope_deg: Maximum terrain slope (degrees)
        steep_terrain_pct: Percentage of terrain with steep slope (> 25 degrees)
    """
    if elevation_map.ndim != 2 or elevation_map.size < 4:
        return {"mean_slope_deg": 0.0, "max_slope_deg": 0.0, "steep_terrain_pct": 0.0}

    gy, gx = np.gradient(elevation_map.astype(np.float32), cell_size_m)
    rise_run = np.sqrt(gx ** 2 + gy ** 2)
    slope_deg = np.degrees(np.arctan(rise_run))

    mean_val = float(np.mean(slope_deg))
    max_val = float(np.max(slope_deg))
    steep_pct = float(np.count_nonzero(slope_deg > 25.0) / slope_deg.size * 100.0)

    return {
        "mean_slope_deg": round(mean_val, 1),
        "max_slope_deg": round(max_val, 1),
        "steep_terrain_pct": round(steep_pct, 1),
    }
