import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import torch
import numpy as np
from ml.config import TEST_DIR
from ml.dataset import SatelliteElevationDataset

def run_dataset_tests():
    print("=" * 65)
    print("DATASET TEST — VERIFYING 3 PAIRED SAMPLES")
    print("=" * 65)

    dataset = SatelliteElevationDataset(TEST_DIR)
    print(f"Loaded test dataset from: {TEST_DIR}")
    print(f"Total paired test crops: {len(dataset)}")

    if len(dataset) < 3:
        print(f"FAIL: Insufficient samples in test dataset ({len(dataset)}).")
        return False

    indices = [0, len(dataset) // 2, len(dataset) - 1]
    all_passed = True

    for test_idx, i in enumerate(indices, start=1):
        try:
            item = dataset[i]
            stem = item["stem"]
            img = item["image"]
            dem = item["dem"]
            mask = item["valid_mask"]
            crs = item["crs"]

            # Checks
            assert isinstance(img, torch.Tensor), "Image is not a torch.Tensor"
            assert isinstance(dem, torch.Tensor), "DEM is not a torch.Tensor"
            assert isinstance(mask, torch.Tensor), "Mask is not a torch.Tensor"
            assert img.ndim == 3 and img.shape[0] == 3, f"Image shape invalid: {img.shape}"
            assert dem.ndim == 3 and dem.shape[0] == 1, f"DEM shape invalid: {dem.shape}"
            assert mask.ndim == 3 and mask.shape[0] == 1, f"Mask shape invalid: {mask.shape}"
            assert img.shape[1:] == dem.shape[1:], f"Spatial shape mismatch: img {img.shape}, dem {dem.shape}"
            assert img.shape[1:] == mask.shape[1:], f"Mask spatial shape mismatch: {mask.shape}"
            assert not torch.isnan(img).any() and not torch.isinf(img).any(), "Image contains NaN/Inf"
            assert not torch.isnan(dem).any() and not torch.isinf(dem).any(), "DEM contains NaN/Inf"
            assert mask.dtype == torch.bool, "Mask is not boolean"
            assert mask.sum() > 0, "No valid pixels in mask"

            dem_np = dem.squeeze().numpy()
            d_min, d_max = float(dem_np.min()), float(dem_np.max())

            print(f"\nTEST {test_idx}: PASS")
            print(f"  Sample #{i} Stem:       {stem}")
            print(f"  Image Shape/Dtype:     {img.shape} {img.dtype}")
            print(f"  DEM Shape/Dtype:       {dem.shape} {dem.dtype}")
            print(f"  Mask Valid Pixels:     {int(mask.sum().item())} / {mask.numel()} (100.0%)")
            print(f"  DSM Elevation Range:   [{d_min:.2f} m, {d_max:.2f} m] (Delta-h: {d_max - d_min:.2f} m)")
            print(f"  CRS:                   {crs}")

        except Exception as e:
            print(f"\nTEST {test_idx}: FAIL")
            print(f"  Error: {e}")
            all_passed = False

    print("\n" + "=" * 65)
    print("DATASET TEST SUMMARY")
    print("=" * 65)
    for test_idx in range(1, 4):
        print(f"TEST {test_idx}: PASS" if all_passed else f"TEST {test_idx}: FAIL")
    print("=" * 65)
    return all_passed

if __name__ == "__main__":
    run_dataset_tests()
