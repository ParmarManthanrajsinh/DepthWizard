import argparse
import csv
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import rasterio
from rasterio.windows import Window

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ml.config import (
    DATA_DIR,
    TEST_DEM_DIR,
    TEST_IMAGES_DIR,
    TRAIN_DEM_DIR,
    TRAIN_IMAGES_DIR,
    VAL_DEM_DIR,
    VAL_IMAGES_DIR,
    VAIHINGEN_ROOT,
)

# Standard ISPRS Vaihingen tile splits (33 total tiles)
# Standard benchmark benchmark split: train: 16 tiles, val: 5 tiles, test: 12 tiles
VAIHINGEN_TRAIN_AREAS = ["1", "3", "5", "7", "13", "17", "21", "23", "26", "32", "37"]
VAIHINGEN_VAL_AREAS = ["11", "15", "28", "30"]
VAIHINGEN_TEST_AREAS = ["2", "4", "6", "8", "10", "12", "14", "16", "20", "22", "24", "27", "29", "31", "33", "34", "35", "38"]

CROP_SIZE = 512
GRID_OFFSETS = [250, 750, 1250, 1750]


def extract_area_id(filename: str) -> str:
    """Extract area number from Vaihingen filenames like 'top_mosaic_09cm_area1.tif' or 'dsm_09cm_matching_area1.tif'."""
    m = re.search(r'area(\d+)', filename, re.IGNORECASE)
    if m:
        return m.group(1)
    return ""


def prepare_vaihingen_dataset(
    vaihingen_root: Path = VAIHINGEN_ROOT,
    crop_size: int = CROP_SIZE,
) -> bool:
    """
    Process ISPRS Vaihingen dataset into 512x512 paired crops with metadata manifest.
    Covers the 'urban / residential' second biome gap.
    """
    print("=" * 65)
    print("ISPRS VAIHINGEN DATASET PREPARATION (MULTI-BIOME EXPANSION)")
    print("=" * 65)
    print(f"Source Root: {vaihingen_root}")

    if not vaihingen_root.exists():
        print(f"\n[NOTICE] Vaihingen root directory does not exist: {vaihingen_root}")
        print("To enable multi-biome Vaihingen processing:")
        print("  1. Download ISPRS Vaihingen 2D Semantic Labeling dataset (Ortho RGB + DSM)")
        print(f"  2. Extract to '{vaihingen_root}' or set VAIHINGEN_ROOT environment variable.")
        print("Expected structure: {VAIHINGEN_ROOT}/dsm/ and {VAIHINGEN_ROOT}/ortho/")
        print("=" * 65)
        return False

    dsm_dirs = [vaihingen_root / "dsm", vaihingen_root / "1_DSM", vaihingen_root]
    rgb_dirs = [vaihingen_root / "ortho", vaihingen_root / "top", vaihingen_root / "2_Ortho_RGB", vaihingen_root]

    dsm_dir = next((d for d in dsm_dirs if d.exists() and len(list(d.glob("*.tif"))) > 0), None)
    rgb_dir = next((d for d in rgb_dirs if d.exists() and len(list(d.glob("*.tif"))) > 0), None)

    if not dsm_dir or not rgb_dir:
        print(f"Could not locate matching DSM and Ortho RGB TIFF files in {vaihingen_root}.")
        return False

    dsm_files = list(dsm_dir.glob("*.tif"))
    rgb_files = list(rgb_dir.glob("*.tif"))

    dsm_map = {extract_area_id(f.name): f for f in dsm_files if extract_area_id(f.name)}
    rgb_map = {extract_area_id(f.name): f for f in rgb_files if extract_area_id(f.name)}

    common_areas = sorted(set(dsm_map.keys()) & set(rgb_map.keys()), key=int)
    print(f"Paired Vaihingen areas found: {len(common_areas)} ({common_areas})")

    if not common_areas:
        print("No matching area IDs found between DSM and Ortho files.")
        return False

    split_map = {}
    for a in VAIHINGEN_TRAIN_AREAS:
        if a in common_areas:
            split_map[a] = "train"
    for a in VAIHINGEN_VAL_AREAS:
        if a in common_areas:
            split_map[a] = "validation"
    for a in VAIHINGEN_TEST_AREAS:
        if a in common_areas:
            split_map[a] = "test"

    # Default unassigned to train
    for a in common_areas:
        if a not in split_map:
            split_map[a] = "train"

    dir_map = {
        "train": (TRAIN_IMAGES_DIR, TRAIN_DEM_DIR),
        "validation": (VAL_IMAGES_DIR, VAL_DEM_DIR),
        "test": (TEST_IMAGES_DIR, TEST_DEM_DIR),
    }

    manifest_rows = []
    crop_counts = {"train": 0, "validation": 0, "test": 0}

    for aid in common_areas:
        split = split_map[aid]
        r_path = rgb_map[aid]
        d_path = dsm_map[aid]
        img_out, dem_out = dir_map[split]

        try:
            with rasterio.open(r_path) as src_r, rasterio.open(d_path) as src_d:
                w_max = min(src_r.width, src_d.width)
                h_max = min(src_r.height, src_d.height)
                crop_idx = 0

                for r_off in GRID_OFFSETS:
                    for c_off in GRID_OFFSETS:
                        if r_off + crop_size > h_max or c_off + crop_size > w_max:
                            continue

                        win = Window(col_off=c_off, row_off=r_off, width=crop_size, height=crop_size)
                        rgb_crop = src_r.read(window=win)
                        dsm_crop = src_d.read(1, window=win)

                        if not np.all(np.isfinite(dsm_crop)):
                            continue
                        d_min, d_max = float(dsm_crop.min()), float(dsm_crop.max())
                        if d_min < -100.0 or d_max > 5000.0:
                            continue

                        stem = f"vaihingen_area{aid}_{crop_idx:03d}"
                        out_r = img_out / f"{stem}.tif"
                        out_d = dem_out / f"{stem}.tif"
                        crop_transform = rasterio.windows.transform(win, src_r.transform)

                        with rasterio.open(
                            out_r, "w", driver="GTiff", height=crop_size, width=crop_size,
                            count=src_r.count, dtype=rgb_crop.dtype, crs=src_r.crs, transform=crop_transform
                        ) as dst:
                            dst.write(rgb_crop)

                        with rasterio.open(
                            out_d, "w", driver="GTiff", height=crop_size, width=crop_size,
                            count=1, dtype="float32", crs=src_d.crs, transform=crop_transform
                        ) as dst:
                            dst.write(dsm_crop.astype(np.float32), 1)

                        manifest_rows.append({
                            "crop_id": stem,
                            "original_tile_id": f"area{aid}",
                            "dataset": "vaihingen",
                            "biome": "residential_suburban",
                            "split": split,
                            "image_path": str(out_r),
                            "dsm_path": str(out_d),
                            "width": crop_size,
                            "height": crop_size,
                            "crs": str(src_r.crs),
                            "dsm_min": round(d_min, 2),
                            "dsm_max": round(d_max, 2),
                            "dsm_delta": round(d_max - d_min, 2),
                        })

                        crop_idx += 1
                        crop_counts[split] += 1

                print(f"Processed Area [{aid}] ({split:10s}): generated {crop_idx} crops")

        except Exception as e:
            print(f"Error processing Area {aid}: {e}")

    # Append to manifest.csv
    manifest_csv = DATA_DIR / "manifest.csv"
    file_exists = manifest_csv.exists()
    with open(manifest_csv, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "crop_id", "original_tile_id", "dataset", "biome", "split",
            "image_path", "dsm_path", "width", "height", "crs", "dsm_min", "dsm_max", "dsm_delta"
        ])
        if not file_exists:
            writer.writeheader()
        writer.writerows(manifest_rows)

    print("-" * 65)
    print("VAIHINGEN DATASET SUMMARY:")
    print(f"Train crops:      {crop_counts['train']}")
    print(f"Validation crops: {crop_counts['validation']}")
    print(f"Test crops:       {crop_counts['test']}")
    print(f"Total crops:      {len(manifest_rows)}")
    print("=" * 65)

    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prepare ISPRS Vaihingen dataset crops")
    parser.add_argument("--root", type=str, default=str(VAIHINGEN_ROOT), help="Vaihingen root dir")
    args = parser.parse_args()

    prepare_vaihingen_dataset(Path(args.root))
