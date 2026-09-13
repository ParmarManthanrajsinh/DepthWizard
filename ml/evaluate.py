import csv
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
from PIL import Image

from ml.config import (
    BASELINE_RESULTS_PATH,
    CHECKPOINT_PATH,
    GLOBAL_CALIBRATION_PATH,
    MANIFEST_PATH,
    RESULTS_DIR,
    TEST_DIR,
)

logger = logging.getLogger("depthwizard.ml.evaluate")


def _extract_valid_pairs(
    pred: Union[np.ndarray, Any],
    target: Union[np.ndarray, Any],
    mask: Optional[Union[np.ndarray, Any]] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """Extract flattened 1D arrays of strictly valid, finite pairs."""
    try:
        import torch
        if isinstance(pred, torch.Tensor):
            pred = pred.detach().cpu().numpy()
        if isinstance(target, torch.Tensor):
            target = target.detach().cpu().numpy()
        if isinstance(mask, torch.Tensor):
            mask = mask.detach().cpu().numpy()
    except ImportError:
        pass

    p = np.asarray(pred, dtype=np.float32).ravel()
    t = np.asarray(target, dtype=np.float32).ravel()

    valid = np.isfinite(p) & np.isfinite(t)
    if mask is not None:
        m = np.asarray(mask, dtype=bool).ravel()
        valid &= m

    return p[valid], t[valid]


def compute_mae(
    pred: Union[np.ndarray, Any],
    target: Union[np.ndarray, Any],
    mask: Optional[Union[np.ndarray, Any]] = None,
) -> float:
    """
    Compute Mean Absolute Error (MAE) exclusively across valid, unmasked pixels.
    Returns float("nan") if no valid pixels exist.
    """
    p_valid, t_valid = _extract_valid_pairs(pred, target, mask)
    if len(p_valid) == 0:
        logger.warning("No valid pixels found for MAE computation.")
        return float("nan")
    return float(np.mean(np.abs(p_valid - t_valid)))


def compute_rmse(
    pred: Union[np.ndarray, Any],
    target: Union[np.ndarray, Any],
    mask: Optional[Union[np.ndarray, Any]] = None,
) -> float:
    """
    Compute Root Mean Squared Error (RMSE) exclusively across valid, unmasked pixels.
    Returns float("nan") if no valid pixels exist.
    """
    p_valid, t_valid = _extract_valid_pairs(pred, target, mask)
    if len(p_valid) == 0:
        logger.warning("No valid pixels found for RMSE computation.")
        return float("nan")
    return float(np.sqrt(np.mean((p_valid - t_valid) ** 2)))


def compute_pearson_correlation(
    pred: Union[np.ndarray, Any],
    target: Union[np.ndarray, Any],
    mask: Optional[Union[np.ndarray, Any]] = None,
) -> float:
    """
    Compute Pearson correlation coefficient r exclusively across valid, unmasked pixels.
    Returns float("nan") if fewer than 2 valid pixels exist or standard deviation is near zero.
    """
    p_valid, t_valid = _extract_valid_pairs(pred, target, mask)
    if len(p_valid) < 2:
        return float("nan")

    std_p = float(np.std(p_valid))
    std_t = float(np.std(t_valid))

    if std_p < 1e-7 or std_t < 1e-7:
        if np.allclose(p_valid, t_valid):
            return 1.0
        return float("nan")

    corr = float(np.corrcoef(p_valid, t_valid)[0, 1])
    return corr if np.isfinite(corr) else float("nan")


def compute_absrel(
    pred: Union[np.ndarray, Any],
    target: Union[np.ndarray, Any],
    mask: Optional[Union[np.ndarray, Any]] = None,
) -> float:
    """
    Compute Absolute Relative Error (AbsRel): mean(|pred - target| / target)
    Computed exclusively for pixels where target > 0.
    """
    p_valid, t_valid = _extract_valid_pairs(pred, target, mask)
    pos_mask = t_valid > 1e-3
    p_pos = p_valid[pos_mask]
    t_pos = t_valid[pos_mask]
    if len(p_pos) == 0:
        return float("nan")
    return float(np.mean(np.abs(p_pos - t_pos) / t_pos))


def compute_deltas(
    pred: Union[np.ndarray, Any],
    target: Union[np.ndarray, Any],
    mask: Optional[Union[np.ndarray, Any]] = None,
) -> Tuple[float, float, float]:
    """
    Compute standard threshold accuracy metrics:
      delta1: % pixels with max(pred/target, target/pred) < 1.25
      delta2: % pixels with max(pred/target, target/pred) < 1.25^2
      delta3: % pixels with max(pred/target, target/pred) < 1.25^3
    Exclusively computed where both pred > 0 and target > 0.
    """
    p_valid, t_valid = _extract_valid_pairs(pred, target, mask)
    pos_mask = (p_valid > 1e-3) & (t_valid > 1e-3)
    p_pos = p_valid[pos_mask]
    t_pos = t_valid[pos_mask]
    if len(p_pos) == 0:
        return float("nan"), float("nan"), float("nan")

    ratio = np.maximum(p_pos / t_pos, t_pos / p_pos)
    d1 = float(np.mean(ratio < 1.25))
    d2 = float(np.mean(ratio < (1.25 ** 2)))
    d3 = float(np.mean(ratio < (1.25 ** 3)))
    return d1, d2, d3


def colorize_jet_heatmap(data: np.ndarray, vmin: Optional[float] = None, vmax: Optional[float] = None) -> np.ndarray:
    """
    Convert a 2D float array into an RGB heatmap using pure NumPy (no matplotlib dependency).
    Blue (low) -> Cyan -> Green -> Yellow -> Red (high).
    """
    d = data.squeeze().astype(np.float32)
    min_val = float(vmin) if vmin is not None else float(np.nanmin(d))
    max_val = float(vmax) if vmax is not None else float(np.nanmax(d))
    
    if max_val > min_val:
        norm = np.clip((d - min_val) / (max_val - min_val), 0.0, 1.0)
    else:
        norm = np.zeros_like(d)

    r = np.clip(1.5 - np.abs(4.0 * norm - 3.0), 0.0, 1.0)
    g = np.clip(1.5 - np.abs(4.0 * norm - 2.0), 0.0, 1.0)
    b = np.clip(1.5 - np.abs(4.0 * norm - 1.0), 0.0, 1.0)

    rgb = np.stack([r, g, b], axis=-1)
    return (rgb * 255.0).astype(np.uint8)


def save_quad_visualization(
    rgb_img: np.ndarray,
    gt_dsm: np.ndarray,
    pred_dsm: np.ndarray,
    err_map: np.ndarray,
    output_path: Path,
) -> None:
    """
    Save 4-panel visual comparison:
    [Input RGB] [Ground Truth DSM] [Predicted DSM] [Absolute Error Heatmap]
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    h, w = rgb_img.shape[:2]

    # Normalize GT DSM and Pred DSM using shared range for fair visual comparison
    all_elev = np.concatenate([gt_dsm.flatten(), pred_dsm.flatten()])
    e_min, e_max = float(np.nanmin(all_elev)), float(np.nanmax(all_elev))

    gt_color = colorize_jet_heatmap(gt_dsm, vmin=e_min, vmax=e_max)
    pred_color = colorize_jet_heatmap(pred_dsm, vmin=e_min, vmax=e_max)
    err_color = colorize_jet_heatmap(err_map, vmin=0.0, vmax=max(5.0, float(np.nanmax(err_map))))

    # Create 4-panel triptych + error
    quad = Image.new("RGB", (w * 4, h))
    quad.paste(Image.fromarray(rgb_img), (0, 0))
    quad.paste(Image.fromarray(gt_color), (w, 0))
    quad.paste(Image.fromarray(pred_color), (w * 2, 0))
    quad.paste(Image.fromarray(err_color), (w * 3, 0))
    quad.save(output_path)


def save_sample_visualizations(
    image: np.ndarray,
    dem: np.ndarray,
    prediction: np.ndarray,
    output_dir: Path = RESULTS_DIR,
) -> Dict[str, Path]:
    """
    Legacy helper preserved for test suite compatibility.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {}

    img_clean = image.copy()
    if img_clean.dtype in (np.float32, np.float64) and img_clean.max() <= 1.0:
        img_clean = (img_clean * 255.0).astype(np.uint8)
    else:
        img_clean = img_clean.astype(np.uint8)

    input_path = output_dir / "sample_input.png"
    Image.fromarray(img_clean).save(input_path)
    paths["sample_input"] = input_path

    dem_clean = dem.squeeze()
    d_min, d_max = float(np.nanmin(dem_clean)), float(np.nanmax(dem_clean))
    dem_norm = ((dem_clean - d_min) / (d_max - d_min) * 255.0).astype(np.uint8) if d_max > d_min else np.zeros_like(dem_clean, dtype=np.uint8)

    gt_path = output_dir / "sample_ground_truth.png"
    Image.fromarray(dem_norm, mode="L").save(gt_path)
    paths["sample_ground_truth"] = gt_path

    pred_clean = prediction.squeeze()
    p_min, p_max = float(np.nanmin(pred_clean)), float(np.nanmax(pred_clean))
    pred_norm = ((pred_clean - p_min) / (p_max - p_min) * 255.0).astype(np.uint8) if p_max > p_min else np.zeros_like(pred_clean, dtype=np.uint8)

    pred_path = output_dir / "sample_prediction.png"
    Image.fromarray(pred_norm, mode="L").save(pred_path)
    paths["sample_prediction"] = pred_path

    h, w = img_clean.shape[:2]
    gt_rgb = np.stack([dem_norm] * 3, axis=-1)
    pred_rgb = np.stack([pred_norm] * 3, axis=-1)

    triptych = Image.new("RGB", (w * 3, h))
    triptych.paste(Image.fromarray(img_clean), (0, 0))
    triptych.paste(Image.fromarray(gt_rgb), (w, 0))
    triptych.paste(Image.fromarray(pred_rgb), (w * 2, 0))
    comp_path = output_dir / "sample_comparison.png"
    triptych.save(comp_path)
    paths["sample_comparison"] = comp_path

    return paths


def extract_tile_id_from_stem(stem: str) -> str:
    """Extract tile identifier from sample stem."""
    parts = stem.split("_")
    if len(parts) >= 3 and parts[0] == "potsdam":
        return f"{parts[1]}_{parts[2]}"
    elif len(parts) >= 2:
        return parts[1]
    return stem


def evaluate_baseline(
    dataset_dir: Optional[Path] = None,
    output_json: Optional[Path] = None,
    output_csv: Optional[Path] = None,
    save_visuals: bool = True,
    max_eval_samples: Optional[int] = None,
    checkpoint_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Evaluate the monocular depth pipeline against ground-truth DSMs across two protocols:
    1. Honest Frozen Global Calibration (Default / Real-world deployment protocol)
       Uses fixed (a, b) fitted exclusively on validation split; zero GT peeking at test time.
    2. Oracle Upper Bound Protocol
       Fits scale/offset per-image against test GT to demonstrate theoretical maximum alignment.
    """
    from ml.dataset import SatelliteElevationDataset
    from ml.inference import DepthAnythingV2Baseline

    target_dir = dataset_dir or TEST_DIR
    results_file = output_json or (RESULTS_DIR / "evaluation.json")
    csv_file = output_csv or (RESULTS_DIR / "evaluation.csv")

    dataset = SatelliteElevationDataset(target_dir)

    print("\n" + "=" * 65)
    print("DEPTHWIZARD ML BENCHMARK — COMPREHENSIVE HELD-OUT EVALUATION")
    print("=" * 65)
    print(f"Target test directory: {target_dir}")
    print(f"Test samples found:    {len(dataset)}")

    if len(dataset) == 0:
        notice = "EVALUATION HALTED: NO TEST SAMPLES FOUND."
        print(f"\n{notice}")
        return {
            "model": "Depth Anything V2",
            "dataset": str(target_dir),
            "status": "NO_DATA",
            "dataset_size": 0,
        }

    # Load frozen global calibration
    frozen_scale, frozen_offset = 1.0, 0.0
    has_frozen_calib = False
    if GLOBAL_CALIBRATION_PATH.exists():
        try:
            with open(GLOBAL_CALIBRATION_PATH, "r") as f:
                cdata = json.load(f)
                frozen_scale = float(cdata.get("scale", 1.0))
                frozen_offset = float(cdata.get("offset_meters", 0.0))
                has_frozen_calib = True
                print(f"Loaded Frozen Global Calibration: scale={frozen_scale:.6f}, offset={frozen_offset:.4f} m")
        except Exception as e:
            logger.warning(f"Could not load global calibration ({e}). Using default identity.")
    else:
        logger.warning(f"Global calibration {GLOBAL_CALIBRATION_PATH} not found. Run scripts/fit_global_calibration.py first.")

    # Load manifest metadata for biome and tile mapping
    manifest_meta: Dict[str, Dict[str, str]] = {}
    if MANIFEST_PATH.exists():
        try:
            with open(MANIFEST_PATH, "r") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    cid = r.get("crop_id")
                    if cid:
                        manifest_meta[cid] = r
        except Exception as e:
            logger.warning(f"Could not load manifest metadata: {e}")

    # Checkpoint initialization
    ckpt_target = checkpoint_path or (CHECKPOINT_PATH if CHECKPOINT_PATH.exists() else None)
    baseline = DepthAnythingV2Baseline(checkpoint_path=ckpt_target)

    # Metric accumulators for Frozen Global Protocol
    mae_list = []
    rmse_list = []
    corr_list = []
    absrel_list = []
    d1_list = []
    d2_list = []
    d3_list = []

    # Metric accumulators for Oracle Upper Bound Protocol
    oracle_mae_list = []
    oracle_rmse_list = []
    oracle_corr_list = []
    oracle_absrel_list = []
    oracle_d1_list = []
    oracle_d2_list = []
    oracle_d3_list = []

    total_valid_pixels = 0
    evaluated_tiles = set()
    biome_records: Dict[str, List[Dict[str, float]]] = {}
    per_sample_records = []

    vis_dir = RESULTS_DIR / "visualizations"
    preds_dir = RESULTS_DIR / "predictions"
    vis_dir.mkdir(parents=True, exist_ok=True)
    preds_dir.mkdir(parents=True, exist_ok=True)

    eval_count = len(dataset) if max_eval_samples is None else min(len(dataset), max_eval_samples)

    for i in range(eval_count):
        item = dataset[i]
        stem = item["stem"]
        img_tensor = item["image"]
        dem_tensor = item["dem"].squeeze().numpy()
        mask = item["valid_mask"].squeeze().numpy()

        meta = manifest_meta.get(stem, {})
        tile_id = meta.get("original_tile_id") or extract_tile_id_from_stem(stem)
        biome = meta.get("biome", "urban")
        evaluated_tiles.add(tile_id)

        # 1. Monocular Relative Depth Prediction
        rel_depth = baseline.predict_relative_depth(img_tensor)

        # 2. Protocol 1: Frozen Global Affine Metric Elevation
        calibrated_elev, stats = baseline.predict_metric_elevation(
            relative_depth=rel_depth,
            reference_dem=dem_tensor,
            valid_mask=mask,
            scale=frozen_scale,
            offset=frozen_offset,
        )

        sample_mae = compute_mae(calibrated_elev, dem_tensor, mask)
        sample_rmse = compute_rmse(calibrated_elev, dem_tensor, mask)
        sample_corr = compute_pearson_correlation(calibrated_elev, dem_tensor, mask)
        sample_absrel = compute_absrel(calibrated_elev, dem_tensor, mask)
        sample_d1, sample_d2, sample_d3 = compute_deltas(calibrated_elev, dem_tensor, mask)

        # 3. Protocol 2: Oracle Upper Bound (per-image fit against GT)
        oracle_elev, oracle_stats = baseline.predict_metric_elevation(
            relative_depth=rel_depth,
            reference_dem=dem_tensor,
            valid_mask=mask,
        )

        o_mae = compute_mae(oracle_elev, dem_tensor, mask)
        o_rmse = compute_rmse(oracle_elev, dem_tensor, mask)
        o_corr = compute_pearson_correlation(oracle_elev, dem_tensor, mask)
        o_absrel = compute_absrel(oracle_elev, dem_tensor, mask)
        o_d1, o_d2, o_d3 = compute_deltas(oracle_elev, dem_tensor, mask)

        err_map = np.abs(calibrated_elev - dem_tensor)
        valid_px = int(np.count_nonzero(mask))
        total_valid_pixels += valid_px

        if np.isfinite(sample_mae):
            mae_list.append(sample_mae)
        if np.isfinite(sample_rmse):
            rmse_list.append(sample_rmse)
        if np.isfinite(sample_corr):
            corr_list.append(sample_corr)
        if np.isfinite(sample_absrel):
            absrel_list.append(sample_absrel)
        if np.isfinite(sample_d1):
            d1_list.append(sample_d1)
        if np.isfinite(sample_d2):
            d2_list.append(sample_d2)
        if np.isfinite(sample_d3):
            d3_list.append(sample_d3)

        if np.isfinite(o_mae):
            oracle_mae_list.append(o_mae)
        if np.isfinite(o_rmse):
            oracle_rmse_list.append(o_rmse)
        if np.isfinite(o_corr):
            oracle_corr_list.append(o_corr)
        if np.isfinite(o_absrel):
            oracle_absrel_list.append(o_absrel)
        if np.isfinite(o_d1):
            oracle_d1_list.append(o_d1)
        if np.isfinite(o_d2):
            oracle_d2_list.append(o_d2)
        if np.isfinite(o_d3):
            oracle_d3_list.append(o_d3)

        # Biome grouping
        if biome not in biome_records:
            biome_records[biome] = []
        biome_records[biome].append({
            "mae_m": sample_mae,
            "rmse_m": sample_rmse,
            "pearson_r": sample_corr,
            "oracle_mae_m": o_mae,
        })

        per_sample_records.append({
            "sample_id": stem,
            "tile_id": tile_id,
            "biome": biome,
            "mae_m": round(sample_mae, 4),
            "rmse_m": round(sample_rmse, 4),
            "pearson_r": round(sample_corr, 4),
            "absrel": round(sample_absrel, 4),
            "delta1": round(sample_d1, 4),
            "delta2": round(sample_d2, 4),
            "delta3": round(sample_d3, 4),
            "oracle_mae_m": round(o_mae, 4),
            "oracle_rmse_m": round(o_rmse, 4),
            "oracle_pearson_r": round(o_corr, 4),
            "valid_pixels": valid_px,
        })

        # Save predictions as npy
        np.save(preds_dir / f"{stem}_pred.npy", calibrated_elev)

        # Save 4-panel visual comparison for first 3 samples
        if i < 3 and save_visuals:
            mean = np.array((0.485, 0.456, 0.406), dtype=np.float32).reshape(3, 1, 1)
            std = np.array((0.229, 0.224, 0.225), dtype=np.float32).reshape(3, 1, 1)
            img_denorm = (img_tensor.numpy() * std + mean) * 255.0
            img_denorm = np.clip(img_denorm, 0, 255).astype(np.uint8)
            img_hwc = np.transpose(img_denorm, (1, 2, 0))

            quad_path = vis_dir / f"{stem}_quad_comparison.png"
            save_quad_visualization(img_hwc, dem_tensor, calibrated_elev, err_map, quad_path)

            if i == 0:
                save_sample_visualizations(
                    image=img_hwc,
                    dem=dem_tensor,
                    prediction=calibrated_elev,
                    output_dir=RESULTS_DIR,
                )

        if (i + 1) % 25 == 0 or (i + 1) == eval_count:
            print(f"Evaluated [{i + 1}/{eval_count}] crops | Frozen MAE={np.mean(mae_list):.2f}m | Oracle MAE={np.mean(oracle_mae_list):.2f}m | Corr={np.mean(corr_list):.3f}")

    avg_mae = float(np.mean(mae_list)) if mae_list else float("nan")
    avg_rmse = float(np.mean(rmse_list)) if rmse_list else float("nan")
    avg_corr = float(np.mean(corr_list)) if corr_list else float("nan")
    avg_absrel = float(np.mean(absrel_list)) if absrel_list else float("nan")
    avg_d1 = float(np.mean(d1_list)) if d1_list else float("nan")
    avg_d2 = float(np.mean(d2_list)) if d2_list else float("nan")
    avg_d3 = float(np.mean(d3_list)) if d3_list else float("nan")

    avg_o_mae = float(np.mean(oracle_mae_list)) if oracle_mae_list else float("nan")
    avg_o_rmse = float(np.mean(oracle_rmse_list)) if oracle_rmse_list else float("nan")
    avg_o_corr = float(np.mean(oracle_corr_list)) if oracle_corr_list else float("nan")
    avg_o_absrel = float(np.mean(oracle_absrel_list)) if oracle_absrel_list else float("nan")
    avg_o_d1 = float(np.mean(oracle_d1_list)) if oracle_d1_list else float("nan")
    avg_o_d2 = float(np.mean(oracle_d2_list)) if oracle_d2_list else float("nan")
    avg_o_d3 = float(np.mean(oracle_d3_list)) if oracle_d3_list else float("nan")

    # Aggregate per-biome metrics
    biome_metrics_summary = {}
    for b_name, recs in biome_records.items():
        biome_metrics_summary[b_name] = {
            "crops_count": len(recs),
            "mae_meters": round(float(np.mean([r["mae_m"] for r in recs])), 4),
            "rmse_meters": round(float(np.mean([r["rmse_m"] for r in recs])), 4),
            "pearson_correlation": round(float(np.mean([r["pearson_r"] for r in recs])), 4),
            "oracle_mae_meters": round(float(np.mean([r["oracle_mae_m"] for r in recs])), 4),
        }

    results_data = {
        "model": "Depth Anything V2 Small (depth-anything/Depth-Anything-V2-Small-hf)",
        "dataset": "ISPRS Potsdam (RGB + DSM)",
        "split": "held-out test",
        "test_tiles": len(evaluated_tiles),
        "test_samples": eval_count,
        "valid_evaluated_pixels": total_valid_pixels,
        "primary_frozen_global_protocol": {
            "description": "Honest benchmark: affine scale and offset frozen from validation split (no test GT peeking)",
            "scale": frozen_scale,
            "offset_meters": frozen_offset,
            "mae_meters": round(avg_mae, 4),
            "rmse_meters": round(avg_rmse, 4),
            "pearson_correlation": round(avg_corr, 4),
            "absrel": round(avg_absrel, 4),
            "delta1": round(avg_d1, 4),
            "delta2": round(avg_d2, 4),
            "delta3": round(avg_d3, 4),
        },
        "oracle_upper_bound_protocol": {
            "description": "Oracle upper bound: scale and offset fit per-image against test GT (theoretical ceiling)",
            "mae_meters": round(avg_o_mae, 4),
            "rmse_meters": round(avg_o_rmse, 4),
            "pearson_correlation": round(avg_o_corr, 4),
            "absrel": round(avg_o_absrel, 4),
            "delta1": round(avg_o_d1, 4),
            "delta2": round(avg_o_d2, 4),
            "delta3": round(avg_o_d3, 4),
        },
        "biome_metrics": biome_metrics_summary,
        # Standard metrics block (Frozen global calibration as primary)
        "metrics": {
            "mae_meters": round(avg_mae, 4),
            "rmse_meters": round(avg_rmse, 4),
            "pearson_correlation": round(avg_corr, 4),
            "absrel": round(avg_absrel, 4),
            "delta1": round(avg_d1, 4),
            "delta2": round(avg_d2, 4),
            "delta3": round(avg_d3, 4),
            "oracle_mae_meters": round(avg_o_mae, 4),
            "oracle_rmse_meters": round(avg_o_rmse, 4),
            "oracle_pearson_correlation": round(avg_o_corr, 4),
        }
    }

    results_file.parent.mkdir(parents=True, exist_ok=True)
    with open(results_file, "w") as f:
        json.dump(results_data, f, indent=4)

    with open(BASELINE_RESULTS_PATH, "w") as f:
        json.dump(results_data, f, indent=4)

    # Save per-sample CSV
    with open(csv_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "sample_id", "tile_id", "biome", "mae_m", "rmse_m", "pearson_r", "absrel",
            "delta1", "delta2", "delta3", "oracle_mae_m", "oracle_rmse_m", "oracle_pearson_r", "valid_pixels"
        ])
        writer.writeheader()
        writer.writerows(per_sample_records)

    print("-" * 65)
    print("MODEL EVALUATION RESULTS (DUAL PROTOCOL REPORT):")
    print(f"Test Tiles (dynamic count): {len(evaluated_tiles)} ({sorted(list(evaluated_tiles))})")
    print(f"Test Samples:             {eval_count}")
    print(f"Valid Evaluated Pixels:   {total_valid_pixels:,}")
    print("-" * 65)
    print(f"[1] FROZEN GLOBAL CALIBRATION (Honest Deployment Protocol):")
    print(f"    MAE:                  {avg_mae:.4f} m")
    print(f"    RMSE:                 {avg_rmse:.4f} m")
    print(f"    Pearson Correlation:  {avg_corr:.4f}")
    print(f"    AbsRel:               {avg_absrel:.4f}")
    print(f"    delta1 (< 1.25):      {avg_d1:.4f} ({avg_d1 * 100:.1f}%)")
    print(f"    delta2 (< 1.25^2):    {avg_d2:.4f} ({avg_d2 * 100:.1f}%)")
    print(f"    delta3 (< 1.25^3):    {avg_d3:.4f} ({avg_d3 * 100:.1f}%)")
    print("-" * 65)
    print(f"[2] ORACLE UPPER BOUND (Per-Image Fit Against GT):")
    print(f"    Oracle MAE:           {avg_o_mae:.4f} m")
    print(f"    Oracle RMSE:          {avg_o_rmse:.4f} m")
    print(f"    Oracle Pearson r:     {avg_o_corr:.4f}")
    print(f"    Oracle delta1:        {avg_o_d1:.4f} ({avg_o_d1 * 100:.1f}%)")
    print("-" * 65)
    print("BIOME BREAKDOWN:")
    for b_name, b_data in biome_metrics_summary.items():
        print(f"  Biome [{b_name.upper()}]: {b_data['crops_count']} crops | Honest MAE={b_data['mae_meters']:.2f}m | Oracle MAE={b_data['oracle_mae_meters']:.2f}m | Corr={b_data['pearson_correlation']:.3f}")
    print("-" * 65)
    print(f"Results JSON:             {results_file}")
    print(f"Results CSV:              {csv_file}")
    print(f"Visualizations saved to:  {vis_dir}")
    print("=" * 65)

    return results_data


if __name__ == "__main__":
    evaluate_baseline()

