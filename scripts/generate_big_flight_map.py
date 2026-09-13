import math
from pathlib import Path
import numpy as np
from PIL import Image

try:
    import rasterio
    from rasterio.transform import from_origin
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False

from app.config import SAMPLES_DIR, OUTPUTS_DIR


def generate_himalayan_corridor(output_path: Path) -> Path:
    """
    Generate a 2.4 km expansive Himalayan Alpine Flight Corridor.
    Features:
    - Deep central canyon / river valley (canyon run for jet)
    - Towering glaciated granite peaks on both flanks
    - High-detail terrain relief with fractal ridgelines
    - Georeferenced GeoTIFF (EPSG:4326) in Central Himalayas
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    res = 1024
    y, x = np.mgrid[:res, :res]

    # Coordinate mapping: center is x=0, y=0 (-1 to +1)
    nx = (x - res / 2.0) / (res / 2.0)
    ny = (y - res / 2.0) / (res / 2.0)

    # 1. Central canyon / valley trough running roughly North-South with subtle curves
    valley_axis = nx - 0.18 * np.sin(ny * 3.5) - 0.08 * np.cos(ny * 7.0)
    dist_to_river = np.abs(valley_axis)

    # Valley floor is low and flat near the river
    valley_profile = np.tanh(dist_to_river * 3.5)

    # 2. Alpine ridges on east and west flanks
    ridges_west = (
        0.55 * np.sin(nx * 8.0 + ny * 3.0) +
        0.28 * np.cos(nx * 16.0 - ny * 7.0) +
        0.14 * np.sin(nx * 32.0 + ny * 15.0)
    )
    ridges_east = (
        0.55 * np.cos(nx * 7.5 - ny * 3.2) +
        0.28 * np.sin(nx * 15.0 + ny * 6.5) +
        0.14 * np.cos(nx * 30.0 - ny * 14.0)
    )
    mountain_massif = np.where(nx < 0, ridges_west, ridges_east)

    # Peak towers: sharp glacial horns
    horns = (
        np.exp(-((nx - 0.65)**2 + (ny - 0.3)**2) / 0.04) * 1.2 +
        np.exp(-((nx + 0.6)**2 + (ny + 0.4)**2) / 0.05) * 1.3 +
        np.exp(-((nx - 0.5)**2 + (ny + 0.6)**2) / 0.04) * 1.1 +
        np.exp(-((nx + 0.7)**2 + (ny - 0.5)**2) / 0.045) * 1.15
    )

    # Combine elevation: valley floor + rising flanks + horns
    elevation = (valley_profile * 0.75 + mountain_massif * 0.25 * valley_profile + horns)
    elevation = np.clip(elevation, 0.02, 1.8)
    elevation = (elevation - elevation.min()) / (elevation.max() - elevation.min())

    # Simulated sunlight for optical satellite appearance (sun from South-East)
    gy, gx = np.gradient(elevation * 80.0)
    sun = np.array([0.55, 0.75, 0.35])
    sun /= np.linalg.norm(sun)
    normal_z = np.ones_like(gx)
    normal = np.stack([-gx, -gy, normal_z], axis=-1)
    norm_len = np.linalg.norm(normal, axis=-1, keepdims=True)
    normal /= np.maximum(norm_len, 1e-6)

    diffuse = np.sum(normal * sun, axis=-1)
    diffuse = np.clip(diffuse, 0.25, 1.0)

    # Palette:
    # High snow (>0.65): brilliant white / glacial ice blue
    # Rock cliffs (0.35 - 0.65): granite grey / slate
    # Alpine vegetation / valley (0.08 - 0.35): deep pine / forest green
    # Glacial river (dist_to_river < 0.025): turquoise water
    rgb = np.zeros((res, res, 3), dtype=np.float32)

    # Glacial river mask
    is_river = dist_to_river < 0.028

    for i in range(res):
        for c in range(3):
            pass # vectorized below

    h = elevation
    # Base terrain colors
    snow_col = np.array([245, 248, 252], dtype=np.float32)
    rock_col = np.array([125, 130, 138], dtype=np.float32)
    pine_col = np.array([38, 62, 42], dtype=np.float32)
    river_col = np.array([36, 115, 142], dtype=np.float32)

    # Elevation blend weights
    w_snow = np.clip((h - 0.58) / 0.18, 0.0, 1.0)[:, :, None]
    w_rock = np.clip((h - 0.28) / 0.20, 0.0, 1.0)[:, :, None]

    mid_terrain = rock_col * w_rock + pine_col * (1.0 - w_rock)
    terrain_rgb = snow_col * w_snow + mid_terrain * (1.0 - w_snow)

    # Apply directional shading
    shaded_rgb = terrain_rgb * diffuse[:, :, None]

    # Overlay glacial river
    river_mask = is_river[:, :, None]
    final_rgb = np.where(river_mask, river_col * (0.8 + 0.2 * diffuse[:, :, None]), shaded_rgb)
    final_uint8 = np.clip(final_rgb, 0, 255).astype(np.uint8)

    if HAS_RASTERIO:
        # Central Himalayas (near Manaslu / Annapurna, lat 28.5N, lon 84.5E)
        # ~2.4 km bounding box
        transform = from_origin(84.48, 28.58, 0.00022, 0.00022)
        with rasterio.open(
            output_path,
            "w",
            driver="GTiff",
            height=res,
            width=res,
            count=3,
            dtype=final_uint8.dtype,
            crs="EPSG:4326",
            transform=transform,
            nodata=0,
        ) as dst:
            for b in range(3):
                dst.write(final_uint8[:, :, b], b + 1)
    else:
        img = Image.fromarray(final_uint8, mode="RGB")
        img.save(output_path)

    print(f"Generated Himalayan flight corridor: {output_path} ({res}x{res})")
    return output_path


if __name__ == "__main__":
    out = SAMPLES_DIR / "sample_himalayan_corridor.tif"
    generate_himalayan_corridor(out)
