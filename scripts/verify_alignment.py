import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
from PIL import Image
import rasterio
from rasterio.windows import Window
from ml.config import POTSDAM_ROOT, RESULTS_DIR as BASE_RESULTS_DIR
from scripts.validate_potsdam import extract_tile_id_rgb, extract_tile_id_dsm

RESULTS_DIR = BASE_RESULTS_DIR / "alignment_check"

def verify_alignment_samples():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    sample_tiles = ["2_10", "3_11", "4_14"]
    
    dsm_dir = POTSDAM_ROOT / "1_DSM"
    rgb_dir = POTSDAM_ROOT / "2_Ortho_RGB"

    rgb_map = {extract_tile_id_rgb(f.name): f for f in rgb_dir.glob("*.tif")}
    dsm_map = {extract_tile_id_dsm(f.name): f for f in dsm_dir.glob("*.tif")}

    print("=" * 65)
    print("RGB / DSM SPATIAL ALIGNMENT VERIFICATION (3 SAMPLES)")
    print("=" * 65)

    alignment_results = []

    for tid in sample_tiles:
        r_path = rgb_map[tid]
        d_path = dsm_map[tid]

        with rasterio.open(r_path) as src_r, rasterio.open(d_path) as src_d:
            print(f"\n--- Checking Tile [{tid}] ---")
            print(f"RGB: {r_path.name} | Shape: ({src_r.height}, {src_r.width}) | Res: {src_r.res} | CRS: {src_r.crs}")
            print(f"DSM: {d_path.name} | Shape: ({src_d.height}, {src_d.width}) | Res: {src_d.res} | CRS: {src_d.crs}")
            
            # Check upper-left corner coordinates match
            r_bounds = src_r.bounds
            d_bounds = src_d.bounds
            bounds_match = (
                abs(r_bounds.left - d_bounds.left) < 1e-4 and
                abs(r_bounds.top - d_bounds.top) < 1e-4
            )
            print(f"Top-Left Spatial Origin Aligned: {bounds_match}")

            # Define sample 512x512 crop window in center
            cx = (min(src_r.width, src_d.width) - 512) // 2
            cy = (min(src_r.height, src_d.height) - 512) // 2
            win = Window(col_off=cx, row_off=cy, width=512, height=512)

            rgb_crop = src_r.read(window=win) # (3, 512, 512)
            dsm_crop = src_d.read(1, window=win) # (512, 512)

            # Compute crop transform
            crop_transform = rasterio.windows.transform(win, src_r.transform)

            # Save RGB crop as GeoTIFF and PNG
            rgb_tif_path = RESULTS_DIR / f"align_{tid}_rgb.tif"
            rgb_png_path = RESULTS_DIR / f"align_{tid}_rgb.png"
            with rasterio.open(
                rgb_tif_path, "w",
                driver="GTiff",
                height=512, width=512,
                count=3, dtype=rgb_crop.dtype,
                crs=src_r.crs,
                transform=crop_transform
            ) as dst:
                dst.write(rgb_crop)

            # Transpose to (H, W, 3) for PIL
            rgb_hwc = np.transpose(rgb_crop, (1, 2, 0))
            Image.fromarray(rgb_hwc).save(rgb_png_path)

            # Save DSM crop as GeoTIFF and normalized PNG
            dsm_tif_path = RESULTS_DIR / f"align_{tid}_dsm.tif"
            dsm_png_path = RESULTS_DIR / f"align_{tid}_dsm.png"
            with rasterio.open(
                dsm_tif_path, "w",
                driver="GTiff",
                height=512, width=512,
                count=1, dtype="float32",
                crs=src_d.crs,
                transform=crop_transform
            ) as dst:
                dst.write(dsm_crop.astype(np.float32), 1)

            # Normalize DSM for visual inspection
            d_min, d_max = float(np.nanmin(dsm_crop)), float(np.nanmax(dsm_crop))
            if d_max > d_min:
                d_norm = ((dsm_crop - d_min) / (d_max - d_min) * 255.0).astype(np.uint8)
            else:
                d_norm = np.zeros_like(dsm_crop, dtype=np.uint8)
            Image.fromarray(d_norm, mode="L").save(dsm_png_path)

            print(f"Crop Pixel Offset: ({cx}, {cy})")
            print(f"DSM Range in crop: [{d_min:.2f} m, {d_max:.2f} m] (Dh = {d_max - d_min:.2f} m)")
            print(f"Saved RGB crop: {rgb_png_path.name}")
            print(f"Saved DSM crop: {dsm_png_path.name}")

            alignment_results.append({
                "tile_id": tid,
                "bounds_match": bounds_match,
                "crop_offset": [cx, cy],
                "dsm_elevation_min": d_min,
                "dsm_elevation_max": d_max,
                "dsm_elevation_delta": d_max - d_min,
                "rgb_crop_path": str(rgb_tif_path),
                "dsm_crop_path": str(dsm_tif_path),
                "aligned": bounds_match and np.all(np.isfinite(dsm_crop))
            })

    print("\n" + "=" * 65)
    all_pass = all(r["aligned"] for r in alignment_results)
    print(f"Alignment Verification Status: {'PASS' if all_pass else 'FAIL'}")
    print("=" * 65)
    return alignment_results

if __name__ == "__main__":
    results = verify_alignment_samples()
