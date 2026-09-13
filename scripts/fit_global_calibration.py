import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.pipeline.calibration import fit_linear_scale_offset
from ml.config import (
    DATA_DIR,
    GLOBAL_CALIBRATION_PATH,
    RESULTS_DIR,
    VAL_DIR,
)
from ml.dataset import SatelliteElevationDataset
from ml.evaluate import compute_mae, compute_pearson_correlation, compute_rmse
from ml.inference import DepthAnythingV2Baseline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("depthwizard.ml.fit_global_calibration")


def fit_global_affine_calibration(
    val_dir: Path = VAL_DIR,
    output_path: Path = GLOBAL_CALIBRATION_PATH,
    max_samples: Optional[int] = None,
    pixel_subsample_per_crop: int = 5000,
    random_seed: int = 42,
) -> Dict[str, Any]:
    """
    Fit a single global affine calibration (h_metric = a * d_rel + b) exclusively
    across the validation split to establish an honest, defensible benchmark protocol.
    Ground-truth is NEVER touched at test time for calibration fitting.
    """
    print("=" * 65)
    print("FITTING FROZEN GLOBAL AFFINE CALIBRATION (VALIDATION SPLIT)")
    print("=" * 65)
    print(f"Validation directory:       {val_dir}")
    print(f"Target calibration artifact: {output_path}")

    dataset = SatelliteElevationDataset(val_dir)
    total_crops = len(dataset)
    print(f"Validation crops available: {total_crops}")

    if total_crops == 0:
        raise RuntimeError(f"No validation crops found in {val_dir}")

    eval_count = total_crops if max_samples is None else min(total_crops, max_samples)
    baseline = DepthAnythingV2Baseline()

    rng = np.random.RandomState(random_seed)
    all_rel_depth_samples: List[np.ndarray] = []
    all_gt_elevation_samples: List[np.ndarray] = []

    print(f"Evaluating {eval_count} validation crops (subsampling up to {pixel_subsample_per_crop} pixels/crop)...")

    for i in range(eval_count):
        item = dataset[i]
        img_tensor = item["image"]
        dem_np = item["dem"].squeeze().numpy()
        mask_np = item["valid_mask"].squeeze().numpy()

        # Predict dimensionless relative depth
        rel_depth = baseline.predict_relative_depth(img_tensor)

        # Extract strictly valid pairs
        valid = mask_np & np.isfinite(rel_depth) & np.isfinite(dem_np)
        x_valid = rel_depth[valid]
        y_valid = dem_np[valid]

        if len(x_valid) == 0:
            continue

        if len(x_valid) > pixel_subsample_per_crop:
            idx = rng.choice(len(x_valid), size=pixel_subsample_per_crop, replace=False)
            x_sub = x_valid[idx]
            y_sub = y_valid[idx]
        else:
            x_sub = x_valid
            y_sub = y_valid

        all_rel_depth_samples.append(x_sub)
        all_gt_elevation_samples.append(y_sub)

        if (i + 1) % 25 == 0 or (i + 1) == eval_count:
            print(f"  Processed [{i + 1}/{eval_count}] val crops | Collected {sum(len(s) for s in all_rel_depth_samples):,} pixels")

    x_pooled = np.concatenate(all_rel_depth_samples).astype(np.float64)
    y_pooled = np.concatenate(all_gt_elevation_samples).astype(np.float64)

    print("-" * 65)
    print(f"Fitting global affine on {len(x_pooled):,} pooled validation pixels...")

    scale, offset, rmse, mae, corr = fit_linear_scale_offset(x_pooled, y_pooled)

    # Compute validation predictions with fitted global affine
    y_pred = scale * x_pooled + offset
    val_mae = compute_mae(y_pred, y_pooled)
    val_rmse = compute_rmse(y_pred, y_pooled)
    val_corr = compute_pearson_correlation(y_pred, y_pooled)

    calibration_payload = {
        "protocol": "frozen_global_affine",
        "provenance": "Fitted exclusively on validation split; frozen for held-out test evaluation",
        "scale": round(float(scale), 6),
        "offset_meters": round(float(offset), 6),
        "val_crops_evaluated": eval_count,
        "pooled_pixels": int(len(x_pooled)),
        "val_mae_meters": round(float(val_mae), 4),
        "val_rmse_meters": round(float(val_rmse), 4),
        "val_pearson_correlation": round(float(val_corr), 4),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(calibration_payload, f, indent=4)

    print(f"Global scale (a):       {scale:.6f}")
    print(f"Global offset (b):      {offset:.6f} m")
    print(f"Validation MAE:         {val_mae:.4f} m")
    print(f"Validation RMSE:        {val_rmse:.4f} m")
    print(f"Validation Pearson (r): {val_corr:.4f}")
    print(f"Saved frozen calibration artifact to: {output_path}")
    print("=" * 65)

    return calibration_payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fit frozen global affine calibration on validation split.")
    parser.add_argument("--max-samples", type=int, default=None, help="Max val crops to evaluate (default: all)")
    parser.add_argument("--pixels-per-crop", type=int, default=5000, help="Subsampled pixels per crop")
    args = parser.parse_args()

    fit_global_affine_calibration(
        max_samples=args.max_samples,
        pixel_subsample_per_crop=args.pixels_per_crop,
    )
