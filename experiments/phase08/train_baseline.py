import os
import sys
import json
from pathlib import Path
import random
import torch
import numpy as np
from torch.utils.data import DataLoader
from transformers import AutoModelForDepthEstimation

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from ml.datasets.gamus_dataset import GAMUSDataset
from ml.losses import CombinedDepthLoss
from ml.evaluate import compute_rmse, compute_mae, compute_pearson_correlation

def set_seed(seed=42):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

def evaluate(model, loader, device):
    model.eval()
    all_preds = []
    all_targets = []
    
    with torch.no_grad():
        for batch in loader:
            imgs = batch["image"].to(device)
            depths = batch["depth"].squeeze(1).numpy()
            masks = batch["valid_mask"].squeeze(1).numpy()
            
            outputs = model(imgs)
            pred = outputs.predicted_depth
            
            if pred.shape[-2:] != depths.shape[-2:]:
                pred = torch.nn.functional.interpolate(
                    pred.unsqueeze(1),
                    size=depths.shape[-2:],
                    mode="bilinear",
                    align_corners=False,
                ).squeeze(1)
            
            pred = pred.cpu().numpy()
            
            for i in range(len(imgs)):
                p = pred[i]
                t = depths[i]
                m = masks[i]
                
                # Normalize prediction
                p_min, p_max = float(p.min()), float(p.max())
                p_norm = (p - p_min) / (p_max - p_min + 1e-7) if p_max > p_min else p
                
                valid = m.astype(bool) & np.isfinite(p_norm) & np.isfinite(t)
                if np.count_nonzero(valid) > 0:
                    # Affine alignment for metric computation (Oracle fit for evaluation bounds)
                    x = p_norm[valid]
                    y = t[valid]
                    
                    A = np.vstack([x, np.ones(len(x))]).T
                    scale, offset = np.linalg.lstsq(A, y, rcond=None)[0]
                    p_aligned = scale * x + offset
                    
                    all_preds.append(p_aligned)
                    all_targets.append(y)

    if not all_preds:
        return {"mae": float("nan"), "rmse": float("nan"), "corr": float("nan")}
        
    all_preds_cat = np.concatenate(all_preds)
    all_targets_cat = np.concatenate(all_targets)
    
    mae = compute_mae(all_preds_cat, all_targets_cat)
    rmse = compute_rmse(all_preds_cat, all_targets_cat)
    corr = compute_pearson_correlation(all_preds_cat, all_targets_cat)
    
    return {"mae": float(mae), "rmse": float(rmse), "corr": float(corr)}

def main():
    # Documentation config
    config = {
        "random_seed": 42,
        "input_resolution": (518, 518),
        "batch_size": 2,
        "num_workers": 0,
        "optimizer": "AdamW",
        "learning_rate": 5e-5,
        "scheduler": "None",
        "loss": "CombinedDepthLoss(SSI + 0.5*Grad)",
        "frozen_layers": "backbone",
        "trainable_layers": "neck + head",
        "epochs": 1,
        "device": "cuda" if torch.cuda.is_available() else "cpu"
    }
    
    set_seed(config["random_seed"])
    device = config["device"]
    
    print("Initializing GAMUS Baseline Experiment")
    
    train_dataset = GAMUSDataset("data/GAMUS/raw", split="train", target_size=config["input_resolution"])
    val_dataset = GAMUSDataset("data/GAMUS/raw", split="val", target_size=config["input_resolution"])
    test_dataset = GAMUSDataset("data/GAMUS/raw", split="test", target_size=config["input_resolution"])
    
    train_loader = DataLoader(train_dataset, batch_size=config["batch_size"], shuffle=True, num_workers=config["num_workers"])
    val_loader = DataLoader(val_dataset, batch_size=config["batch_size"], shuffle=False, num_workers=config["num_workers"])
    test_loader = DataLoader(test_dataset, batch_size=config["batch_size"], shuffle=False, num_workers=config["num_workers"])
    
    model_name = "depth-anything/Depth-Anything-V2-Small-hf"
    model = AutoModelForDepthEstimation.from_pretrained(model_name).to(device)
    
    if hasattr(model, "backbone"):
        for param in model.backbone.parameters():
            param.requires_grad = False
            
    criterion = CombinedDepthLoss()
    optimizer = torch.optim.AdamW(filter(lambda p: p.requires_grad, model.parameters()), lr=config["learning_rate"])
    
    print("\nStarting Training (1 Epoch)...")
    model.train()
    for batch_idx, batch in enumerate(train_loader):
        imgs = batch["image"].to(device)
        depths = batch["depth"].to(device)
        masks = batch["valid_mask"].to(device)
        
        optimizer.zero_grad()
        outputs = model(imgs)
        pred = outputs.predicted_depth
        
        if pred.shape[-2:] != depths.shape[-2:]:
            pred = torch.nn.functional.interpolate(pred.unsqueeze(1), size=depths.shape[-2:], mode="bilinear", align_corners=False).squeeze(1)
            
        loss, _, _ = criterion(pred, depths, masks)
        loss.backward()
        optimizer.step()
        
    print("\nEvaluating on Validation Set...")
    val_metrics = evaluate(model, val_loader, device)
    print(f"  Val MAE: {val_metrics['mae']:.2f}m, RMSE: {val_metrics['rmse']:.2f}m, Corr: {val_metrics['corr']:.4f}")
    
    print("\nEvaluating on Test Set...")
    test_metrics = evaluate(model, test_loader, device)
    print(f"  Test MAE: {test_metrics['mae']:.2f}m, RMSE: {test_metrics['rmse']:.2f}m, Corr: {test_metrics['corr']:.4f}")
    
    # Checkpoint integrity
    ckpt_dir = Path("experiments/phase08/checkpoints")
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    metrics_dir = Path("experiments/phase08/metrics")
    metrics_dir.mkdir(parents=True, exist_ok=True)
    
    ckpt_path = ckpt_dir / "baseline_gamus_epoch1.pt"
    torch.save({
        "epoch": 1,
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        "config": config,
        "val_metrics": val_metrics,
        "test_metrics": test_metrics
    }, ckpt_path)
    
    with open(metrics_dir / "baseline_metrics.json", "w") as f:
        json.dump({"val": val_metrics, "test": test_metrics, "config": config}, f, indent=2)
        
    print(f"\nExperiment complete. Checkpoint saved to {ckpt_path}")

if __name__ == "__main__":
    main()
