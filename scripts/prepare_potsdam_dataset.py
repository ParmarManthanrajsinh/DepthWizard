import csv
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import rasterio
from rasterio.windows import Window

from ml.config import (
    DATA_DIR,
    POTSDAM_ROOT,
    TRAIN_DEM_DIR,
    TRAIN_IMAGES_DIR,
    VAL_DEM_DIR,
    VAL_IMAGES_DIR,
    TEST_DEM_DIR,
    TEST_IMAGES_DIR,
)
from scripts.validate_potsdam import extract_tile_id_rgb, extract_tile_id_dsm

# Deterministic tile split (Random seed 42)
TRAIN_TILES = [
    '2_10', '2_13', '2_14', '3_10', '3_14', '4_10', '4_11', '4_12', '4_13',
    '5_10', '5_12', '5_13', '5_14', '6_10', '6_11', '6_12', '6_14', '6_15',
    '6_7', '6_9', '7_10', '7_12', '7_13', '7_7', '7_8', '7_9'
]
VAL_TILES = ['2_12', '3_11', '5_15', '6_13', '6_8', '7_11']
TEST_TILES = ['2_11', '3_12', '3_13', '4_14', '4_15', '5_11']

CROP_SIZE = 512
# 5x5 grid across 6000x6000 tile (25 crops per tile)
GRID_OFFSETS = [500, 1500, 2500, 3500, 4500]

def prepare_dataset():
    print("=" * 65)
    print("PREPARING POTSDAM PAIRED RGB + DSM 512x512 CROPS")
    print("=" * 65)
    print(f"Train tiles ({len(TRAIN_TILES)}): {TRAIN_TILES}")
    print(f"Val tiles   ({len(VAL_TILES)}): {VAL_TILES}")
    print(f"Test tiles  ({len(TEST_TILES)}): {TEST_TILES}")
    print(f"Grid offsets per tile: {GRID_OFFSETS} -> 25 crops per tile")
    print("-" * 65)

    dsm_dir = POTSDAM_ROOT / "1_DSM"
    rgb_dir = POTSDAM_ROOT / "2_Ortho_RGB"

    rgb_map = {extract_tile_id_rgb(f.name): f for f in rgb_dir.glob("*.tif")}
    dsm_map = {extract_tile_id_dsm(f.name): f for f in dsm_dir.glob("*.tif")}

    split_map = {}
    for tid in TRAIN_TILES:
        split_map[tid] = "train"
    for tid in VAL_TILES:
        split_map[tid] = "validation"
    for tid in TEST_TILES:
        split_map[tid] = "test"

    dir_map = {
        "train": (TRAIN_IMAGES_DIR, TRAIN_DEM_DIR),
        "validation": (VAL_IMAGES_DIR, VAL_DEM_DIR),
        "test": (TEST_IMAGES_DIR, TEST_DEM_DIR),
    }

    manifest_rows = []
    tile_manifest_rows = []

    crop_counts = {"train": 0, "validation": 0, "test": 0}

    for tid, split in split_map.items():
        r_path = rgb_map[tid]
        d_path = dsm_map[tid]
        img_out_dir, dem_out_dir = dir_map[split]

        with rasterio.open(r_path) as src_r, rasterio.open(d_path) as src_d:
            w_max = min(src_r.width, src_d.width)
            h_max = min(src_r.height, src_d.height)

            tile_manifest_rows.append({
                "split": split,
                "tile_id": tid,
                "image_path": str(r_path),
                "dsm_path": str(d_path),
                "width": src_r.width,
                "height": src_r.height,
                "crs": str(src_r.crs),
            })

            crop_idx = 0
            for row_off in GRID_OFFSETS:
                for col_off in GRID_OFFSETS:
                    if row_off + CROP_SIZE > h_max or col_off + CROP_SIZE > w_max:
                        continue

                    win = Window(col_off=col_off, row_off=row_off, width=CROP_SIZE, height=CROP_SIZE)
                    rgb_crop = src_r.read(window=win)
                    dsm_crop = src_d.read(1, window=win)

                    # Validate crop (ensure finite, plausible elevation)
                    if not np.all(np.isfinite(dsm_crop)):
                        continue
                    d_min, d_max = float(dsm_crop.min()), float(dsm_crop.max())
                    if d_min < -100.0 or d_max > 5000.0:
                        continue

                    crop_stem = f"potsdam_{tid}_{crop_idx:03d}"
                    crop_r_path = img_out_dir / f"{crop_stem}.tif"
                    crop_d_path = dem_out_dir / f"{crop_stem}.tif"

                    crop_transform = rasterio.windows.transform(win, src_r.transform)

                    # Save RGB crop GeoTIFF
                    with rasterio.open(
                        crop_r_path, "w",
                        driver="GTiff",
                        height=CROP_SIZE, width=CROP_SIZE,
                        count=3, dtype=rgb_crop.dtype,
                        crs=src_r.crs,
                        transform=crop_transform
                    ) as dst:
                        dst.write(rgb_crop)

                    # Save DSM crop GeoTIFF
                    with rasterio.open(
                        crop_d_path, "w",
                        driver="GTiff",
                        height=CROP_SIZE, width=CROP_SIZE,
                        count=1, dtype="float32",
                        crs=src_d.crs,
                        transform=crop_transform
                    ) as dst:
                        dst.write(dsm_crop.astype(np.float32), 1)

                    manifest_rows.append({
                        "crop_id": crop_stem,
                        "original_tile_id": tid,
                        "dataset": "potsdam",
                        "biome": "urban",
                        "split": split,
                        "image_path": str(crop_r_path),
                        "dsm_path": str(crop_d_path),
                        "width": CROP_SIZE,
                        "height": CROP_SIZE,
                        "crs": str(src_r.crs),
                        "dsm_min": round(d_min, 2),
                        "dsm_max": round(d_max, 2),
                        "dsm_delta": round(d_max - d_min, 2),
                    })

                    crop_idx += 1
                    crop_counts[split] += 1

        print(f"Processed Tile [{tid}] ({split:10s}): generated {crop_idx} crops")

    # Write manifests
    manifest_csv = DATA_DIR / "manifest.csv"
    with open(manifest_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "crop_id", "original_tile_id", "dataset", "biome", "split", "image_path", "dsm_path",
            "width", "height", "crs", "dsm_min", "dsm_max", "dsm_delta"
        ])
        writer.writeheader()
        writer.writerows(manifest_rows)

    tiles_csv = DATA_DIR / "tiles_manifest.csv"
    for r in tile_manifest_rows:
        r["dataset"] = "potsdam"
        r["biome"] = "urban"
    with open(tiles_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "split", "tile_id", "dataset", "biome", "image_path", "dsm_path", "width", "height", "crs"
        ])
        writer.writeheader()
        writer.writerows(tile_manifest_rows)

    print("-" * 65)
    print("DATASET PREPARATION SUMMARY:")
    print(f"Train crops:      {crop_counts['train']} in {TRAIN_IMAGES_DIR}")
    print(f"Validation crops: {crop_counts['validation']} in {VAL_IMAGES_DIR}")
    print(f"Test crops:       {crop_counts['test']} in {TEST_IMAGES_DIR}")
    print(f"Total crops:      {len(manifest_rows)}")
    print(f"Saved manifest:   {manifest_csv}")
    print(f"Saved tiles csv:  {tiles_csv}")
    print("=" * 65)

if __name__ == "__main__":
    prepare_dataset()
