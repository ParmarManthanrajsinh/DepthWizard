import math
from pathlib import Path
import numpy as np
from PIL import Image

from app.config import SAMPLES_DIR


def create_sample_crater(output_path: Path) -> Path:
    """Generate a high-contrast synthetic impact crater optical image (PNG)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    res = 512
    y, x = np.ogrid[:res, :res]
    cx, cy = res / 2.0, res / 2.0
    r = np.sqrt((x - cx) ** 2 + (y - cy) ** 2) / (res / 2.0)

    # Crater profile: central peak + rim + ejecta
    crater_depth = np.exp(-((r / 0.5) ** 2)) * -0.8
    rim = np.exp(-(((r - 0.5) / 0.1) ** 2)) * 0.7
    central_peak = np.exp(-((r / 0.1) ** 2)) * 0.4
    noise = np.sin(x * 0.1) * np.cos(y * 0.1) * 0.05
    height = crater_depth + rim + central_peak + noise

    # Simulated directional lighting (sun from top-left)
    gy, gx = np.gradient(height)
    sun = np.array([-0.7, -0.7, 0.5])
    sun /= np.linalg.norm(sun)
    normal_z = np.ones_like(gx)
    normal = np.stack([-gx, -gy, normal_z], axis=-1)
    norm_len = np.linalg.norm(normal, axis=-1, keepdims=True)
    normal /= np.maximum(norm_len, 1e-6)
    
    diffuse = np.sum(normal * sun, axis=-1)
    diffuse = np.clip(diffuse, 0.1, 1.0)

    # Desert/Martian optical palette
    r_ch = (diffuse * 210 + 30).astype(np.uint8)
    g_ch = (diffuse * 140 + 20).astype(np.uint8)
    b_ch = (diffuse * 90 + 15).astype(np.uint8)

    img_arr = np.stack([r_ch, g_ch, b_ch], axis=-1)
    img = Image.fromarray(img_arr, mode="RGB")
    img.save(output_path, format="PNG")
    print(f"Generated sample crater: {output_path}")
    return output_path


def create_sample_himalayas(output_path: Path) -> Path:
    """Generate a synthetic alpine valley with GeoTIFF spatial tags (TIFF)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    res = 512
    y, x = np.mgrid[:res, :res]

    # Mountain ridges and valleys
    ridge1 = np.sin(x * 0.03 + y * 0.01) * 0.5
    ridge2 = np.cos(x * 0.015 - y * 0.025) * 0.4
    valley = np.sin((x + y) * 0.01) * 0.3
    height = ridge1 + ridge2 + valley

    gy, gx = np.gradient(height)
    sun = np.array([-0.6, -0.6, 0.7])
    sun /= np.linalg.norm(sun)
    normal = np.stack([-gx, -gy, np.ones_like(gx)], axis=-1)
    normal /= np.maximum(np.linalg.norm(normal, axis=-1, keepdims=True), 1e-6)
    
    diffuse = np.clip(np.sum(normal * sun, axis=-1), 0.15, 1.0)

    # Snow peaks & pine green valley
    snow_mask = height > 0.3
    r_ch = np.where(snow_mask, 230 * diffuse, 60 * diffuse + 20).astype(np.uint8)
    g_ch = np.where(snow_mask, 240 * diffuse, 100 * diffuse + 30).astype(np.uint8)
    b_ch = np.where(snow_mask, 255 * diffuse, 50 * diffuse + 20).astype(np.uint8)

    img_arr = np.stack([r_ch, g_ch, b_ch], axis=-1)
    img = Image.fromarray(img_arr, mode="RGB")

    # Save with basic GeoTIFF tags (ModelTiepoint, ModelPixelScale)
    # Tiepoint at (0, 0, 0) -> Lon 78.5, Lat 30.5, Elev 0 (Garhwal Himalayas)
    # Scale = 0.000277 degrees (~30m per pixel)
    try:
        from PIL.TiffImagePlugin import ImageFileDirectory_v2
        ifd = ImageFileDirectory_v2()
        # Tag 33550: ModelPixelScaleTag (scale_x, scale_y, scale_z)
        ifd[33550] = (0.00027, 0.00027, 0.0)
        # Tag 33922: ModelTiepointTag (I, J, K, X, Y, Z)
        ifd[33922] = (0.0, 0.0, 0.0, 78.50, 30.50, 0.0)
        # Tag 34735: GeoKeyDirectoryTag (ModelTypeGeographic, GeographicTypeWGS84)
        ifd[34735] = (1, 1, 0, 2, 1024, 0, 1, 2, 2048, 0, 1, 4326)
        img.save(output_path, format="TIFF", tiffinfo=ifd)
    except Exception:
        img.save(output_path, format="TIFF")

    print(f"Generated sample Himalayas GeoTIFF: {output_path}")
    return output_path


def generate_all_samples() -> None:
    crater_path = SAMPLES_DIR / "sample_crater.png"
    himalayas_path = SAMPLES_DIR / "sample_himalayas.tif"

    if not crater_path.exists():
        create_sample_crater(crater_path)
    if not himalayas_path.exists():
        create_sample_himalayas(himalayas_path)


if __name__ == "__main__":
    generate_all_samples()
