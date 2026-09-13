import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.pipeline.calibration import fit_linear_scale_offset
from ml.config import (
    CHECKPOINT_PATH,
    DATA_DIR,
    DEFAULT_BATCH_SIZE,
    DEPTH_MODEL_NAME,
    DEVICE,
    GLOBAL_CALIBRATION_PATH,
    RESULTS_DIR,
    TRAIN_DIR,
    TRAINING_LOG_PATH,
    VAL_DIR,
)
from ml.dataset import SatelliteElevationDataset
from ml.evaluate import compute_mae, compute_pearson_correlation, compute_rmse
from ml.losses import CombinedDepthLoss

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("depthwizard.ml.train")


def geospatial_augment(
    image: torch.Tensor,
    dem: torch.Tensor,
    mask: torch.Tensor,
) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """
    Apply geospatially valid geometric augmentations:
    - Random horizontal flip (p=0.5)
    - Random vertical flip (p=0.5)
    - Random 90-degree rotations (k in {0, 1, 2, 3})
    Maintains exact spatial co-registration between image, elevation, and validity mask.
    """
    if torch.rand(1).item() > 0.5:
        image = torch.flip(image, dims=[-1])
        dem = torch.flip(dem, dims=[-1])
        mask = torch.flip(mask, dims=[-1])

    if torch.rand(1).item() > 0.5:
        image = torch.flip(image, dims=[-2])
        dem = torch.flip(dem, dims=[-2])
        mask = torch.flip(mask, dims=[-2])

    k = int(torch.randint(0, 4, (1,)).item())
    if k > 0:
        image = torch.rot90(image, k=k, dims=[-2, -1])
        dem = torch.rot90(dem, k=k, dims=[-2, -1])
        mask = torch.rot90(mask, k=k, dims=[-2, -1])

    return image, dem, mask


def build_trainable_model(
    model_name: str = DEPTH_MODEL_NAME,
    freeze_backbone: bool = True,
) -> Tuple[nn.Module, Any]:
    """
    Load Depth Anything V2 model and freeze DINOv2 encoder backbone.
    Fine-tunes the DPT depth head and reassemble neck layers.
    """
    from transformers import AutoImageProcessor, AutoModelForDepthEstimation

    logger.info(f"Instantiating model from '{model_name}'...")
    processor = AutoImageProcessor.from_pretrained(model_name)
    model = AutoModelForDepthEstimation.from_pretrained(model_name)

    if freeze_backbone and hasattr(model, "backbone"):
        logger.info("Freezing DINOv2 encoder backbone...")
        for p in model.backbone.parameters():
            p.requires_grad = False

    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    frozen_params = sum(p.numel() for p in model.parameters() if not p.requires_grad)
    logger.info(f"Model parameters: {trainable_params:,} trainable | {frozen_params:,} frozen")

    return model, processor


def evaluate_val_split(
    model: nn.Module,
    val_dataset: SatelliteElevationDataset,
    device: str,
    max_samples: int = 50,
    stride: int = 4,
) -> Dict[str, float]:
    """
    Evaluate validation split under frozen global affine calibration.
    Returns validation MAE, RMSE, Pearson r.
    """
    model.eval()
    all_preds = []
    all_targets = []

    eval_count = min(len(val_dataset), max_samples)

    with torch.no_grad():
        for i in range(eval_count):
            item = val_dataset[i]
            img = item["image"].unsqueeze(0).to(device)
            target = item["dem"].squeeze().numpy()
            mask = item["valid_mask"].squeeze().numpy()

            outputs = model(img)
            pred_depth = outputs.predicted_depth.squeeze().cpu().numpy()

            # Resize if needed
            if pred_depth.shape != target.shape:
                h, w = target.shape
                pred_t = torch.from_numpy(pred_depth).unsqueeze(0).unsqueeze(0)
                pred_depth = torch.nn.functional.interpolate(
                    pred_t, size=(h, w), mode="bilinear", align_corners=False
                ).squeeze().numpy()

            # Normalization to [0, 1]
            p_min, p_max = float(pred_depth.min()), float(pred_depth.max())
            p_norm = (pred_depth - p_min) / (p_max - p_min + 1e-7) if p_max > p_min else pred_depth

            valid = mask & np.isfinite(p_norm) & np.isfinite(target)
            if np.count_nonzero(valid) > 0:
                all_preds.append(p_norm[valid][::stride])
                all_targets.append(target[valid][::stride])

    if not all_preds:
        return {"mae": float("nan"), "rmse": float("nan"), "corr": float("nan")}

    x = np.concatenate(all_preds).astype(np.float64)
    y = np.concatenate(all_targets).astype(np.float64)

    scale, offset, rmse, mae, corr = fit_linear_scale_offset(x, y)
    return {
        "mae": float(mae),
        "rmse": float(rmse),
        "corr": float(corr),
        "scale": float(scale),
        "offset": float(offset),
    }


def train_model(
    train_dir: Path = TRAIN_DIR,
    val_dir: Path = VAL_DIR,
    epochs: int = 5,
    batch_size: int = DEFAULT_BATCH_SIZE,
    lr: float = 5e-5,
    weight_decay: float = 1e-4,
    grad_accum_steps: int = 2,
    smoke_test: bool = False,
    max_steps: Optional[int] = None,
    limit_batches: Optional[int] = None,
    resume_path: Optional[Path] = None,
    output_checkpoint: Path = CHECKPOINT_PATH,
    output_log: Path = TRAINING_LOG_PATH,
) -> Dict[str, Any]:
    """
    Main training execution loop.
    Supports RTX 4080 / 4060 (8GB VRAM) mixed-precision training and CPU smoke testing.
    """
    device = "cuda" if torch.cuda.is_available() else "cpu"
    use_amp = (device == "cuda")

    print("=" * 65)
    print(f"DEPTHWIZARD ML FINE-TUNING PIPELINE ({device.upper()})")
    print("=" * 65)
    print(f"Train directory:        {train_dir}")
    print(f"Val directory:          {val_dir}")
    print(f"Batch size:             {batch_size} (effective {batch_size * grad_accum_steps})")
    print(f"Mixed precision (fp16): {use_amp}")
    print(f"Smoke test mode:        {smoke_test}")
    print(f"Output checkpoint:      {output_checkpoint}")
    print("-" * 65)

    train_dataset = SatelliteElevationDataset(train_dir)
    val_dataset = SatelliteElevationDataset(val_dir)

    print(f"Training samples:   {len(train_dataset)}")
    print(f"Validation samples: {len(val_dataset)}")

    if len(train_dataset) == 0:
        logger.warning("No training samples found. Aborting training.")
        return {"status": "NO_TRAINING_DATA"}

    model, processor = build_trainable_model(freeze_backbone=True)
    model.to(device)

    # Trainable parameters (head + neck only)
    trainable_params = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(trainable_params, lr=lr, weight_decay=weight_decay)
    criterion = CombinedDepthLoss(alpha_grad=0.5).to(device)
    scaler = torch.amp.GradScaler('cuda', enabled=use_amp)

    start_epoch = 0
    best_val_mae = float("inf")
    training_history: List[Dict[str, Any]] = []

    # Resume if requested
    if resume_path and Path(resume_path).exists():
        logger.info(f"Resuming training from {resume_path}...")
        ckpt = torch.load(resume_path, map_location=device, weights_only=True)
        model.load_state_dict(ckpt["model_state_dict"], strict=False)
        if "optimizer_state_dict" in ckpt:
            optimizer.load_state_dict(ckpt["optimizer_state_dict"])
        start_epoch = ckpt.get("epoch", 0) + 1
        best_val_mae = ckpt.get("val_mae", float("inf"))

    total_steps = 0
    smoke_max_steps = max_steps if max_steps is not None else (5 if smoke_test else None)
    batch_limit = limit_batches if limit_batches is not None else (2 if smoke_test else None)

    for epoch in range(start_epoch, epochs):
        model.train()
        epoch_loss = 0.0
        epoch_ssi = 0.0
        epoch_grad = 0.0
        batch_count = 0

        # Sample indices
        indices = list(range(len(train_dataset)))
        np.random.shuffle(indices)
        if batch_limit:
            indices = indices[: batch_limit * batch_size]

        optimizer.zero_grad()
        t0 = time.time()

        for b_idx in range(0, len(indices), batch_size):
            batch_slice = indices[b_idx : b_idx + batch_size]
            imgs, dems, masks = [], [], []

            for idx in batch_slice:
                item = train_dataset[idx]
                img_t, dem_t, mask_t = geospatial_augment(
                    item["image"], item["dem"], item["valid_mask"]
                )
                imgs.append(img_t)
                dems.append(dem_t)
                masks.append(mask_t)

            batch_img = torch.stack(imgs).to(device)
            batch_dem = torch.stack(dems).to(device)
            batch_mask = torch.stack(masks).to(device)

            with torch.amp.autocast('cuda', enabled=use_amp, dtype=torch.float16 if use_amp else torch.bfloat16):
                outputs = model(batch_img)
                pred_depth = outputs.predicted_depth

                if pred_depth.shape[-2:] != batch_dem.shape[-2:]:
                    pred_depth = torch.nn.functional.interpolate(
                        pred_depth.unsqueeze(1),
                        size=batch_dem.shape[-2:],
                        mode="bilinear",
                        align_corners=False,
                    ).squeeze(1)

                loss, loss_ssi, loss_g = criterion(pred_depth, batch_dem, batch_mask)
                loss_scaled = loss / grad_accum_steps

            scaler.scale(loss_scaled).backward()

            if (b_idx // batch_size + 1) % grad_accum_steps == 0 or (b_idx + batch_size >= len(indices)):
                scaler.step(optimizer)
                scaler.update()
                optimizer.zero_grad()

            epoch_loss += float(loss.item())
            epoch_ssi += float(loss_ssi.item())
            epoch_grad += float(loss_g.item())
            batch_count += 1
            total_steps += 1

            if smoke_max_steps and total_steps >= smoke_max_steps:
                print(f"Reached max smoke steps ({total_steps}). Terminating training loop.")
                break

        avg_loss = epoch_loss / max(1, batch_count)
        avg_ssi = epoch_ssi / max(1, batch_count)
        avg_grad = epoch_grad / max(1, batch_count)
        elapsed = time.time() - t0

        print(f"Epoch [{epoch + 1}/{epochs}] ({elapsed:.1f}s) | Loss: {avg_loss:.4f} (SSI: {avg_ssi:.4f}, Grad: {avg_grad:.4f})")

        # Validation evaluation
        val_samples = 5 if smoke_test else 50
        val_metrics = evaluate_val_split(model, val_dataset, device, max_samples=val_samples)
        print(f"  Val MAE: {val_metrics['mae']:.4f} m | RMSE: {val_metrics['rmse']:.4f} m | Corr: {val_metrics['corr']:.4f}")

        record = {
            "epoch": epoch + 1,
            "train_loss": round(avg_loss, 4),
            "train_ssi": round(avg_ssi, 4),
            "train_grad": round(avg_grad, 4),
            "val_mae_m": round(val_metrics["mae"], 4),
            "val_rmse_m": round(val_metrics["rmse"], 4),
            "val_corr": round(val_metrics["corr"], 4),
            "elapsed_s": round(elapsed, 2),
        }
        training_history.append(record)

        # Save checkpoint if better or smoke test
        if val_metrics["mae"] < best_val_mae or smoke_test:
            best_val_mae = val_metrics["mae"]
            output_checkpoint.parent.mkdir(parents=True, exist_ok=True)
            torch.save({
                "epoch": epoch,
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "val_mae": best_val_mae,
                "scale": val_metrics.get("scale"),
                "offset": val_metrics.get("offset"),
            }, output_checkpoint)
            print(f"  --> Saved new best checkpoint to {output_checkpoint} (Val MAE: {best_val_mae:.4f}m)")

        if smoke_max_steps and total_steps >= smoke_max_steps:
            break

    # Save training log
    output_log.parent.mkdir(parents=True, exist_ok=True)
    with open(output_log, "w") as f:
        json.dump({
            "model": DEPTH_MODEL_NAME,
            "device": device,
            "epochs_run": len(training_history),
            "best_val_mae_m": best_val_mae if np.isfinite(best_val_mae) else None,
            "history": training_history,
        }, f, indent=2)

    print("=" * 65)
    print("TRAINING RUN COMPLETE")
    print(f"Best Val MAE:  {best_val_mae:.4f} m")
    print(f"Checkpoint:    {output_checkpoint}")
    print(f"Training Log:  {output_log}")
    print("=" * 65)

    return {"status": "SUCCESS", "best_val_mae": best_val_mae, "history": training_history}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DepthWizard ML Fine-Tuning Pipeline")
    parser.add_argument("--epochs", type=int, default=5, help="Number of training epochs")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Batch size")
    parser.add_argument("--lr", type=float, default=5e-5, help="Learning rate")
    parser.add_argument("--grad-accum", type=int, default=2, help="Gradient accumulation steps")
    parser.add_argument("--smoke-test", action="store_true", help="Run rapid smoke test mode")
    parser.add_argument("--max-steps", type=int, default=None, help="Terminate after N steps")
    parser.add_argument("--limit-batches", type=int, default=None, help="Limit batches per epoch")
    parser.add_argument("--resume", type=str, default=None, help="Path to checkpoint to resume from")

    args = parser.parse_args()

    train_model(
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        grad_accum_steps=args.grad_accum,
        smoke_test=args.smoke_test,
        max_steps=args.max_steps,
        limit_batches=args.limit_batches,
        resume_path=Path(args.resume) if args.resume else None,
    )
