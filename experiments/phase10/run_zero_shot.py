import sys
import json
import time
from pathlib import Path
import torch
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ml.dataset import SatelliteElevationDataset
from transformers import AutoModelForDepthEstimation

def main():
    print("Starting Phase 10B GAMUS -> Potsdam Zero-Shot Evaluation")
    
    device = "cuda" if torch.cuda.is_available() else "cpu"
    ckpt_path = Path("experiments/phase08/checkpoints/baseline_gamus_epoch1.pt")
    
    # Load Model
    model = AutoModelForDepthEstimation.from_pretrained("depth-anything/Depth-Anything-V2-Small-hf").to(device)
    checkpoint = torch.load(ckpt_path, map_location=device, weights_only=True)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    
    # Load Potsdam Test Set
    test_dataset = SatelliteElevationDataset(root_dir="data/test")
    test_samples = len(test_dataset)
    print(f"Loaded {test_samples} Potsdam test samples.")
    
    all_preds = []
    all_targets = []
    
    start_time = time.time()
    
    # Zero-Shot Forward Passes (No Training, No Calibration Fitting)
    with torch.no_grad():
        for i in range(test_samples):
            item = test_dataset[i]
            img = item["image"].unsqueeze(0).to(device)
            dem = item["dem"].unsqueeze(0).to(device)
            mask = item["valid_mask"].unsqueeze(0).to(device)
            
            outputs = model(img)
            pred = outputs.predicted_depth
            
            if pred.shape[-2:] != dem.shape[-2:]:
                pred = torch.nn.functional.interpolate(pred.unsqueeze(1), size=dem.shape[-2:], mode="bilinear").squeeze(1)
            
            # Mask out invalid pixels
            valid_p = pred[mask.squeeze(0)]
            valid_t = dem[mask]
            
            all_preds.append(valid_p.cpu())
            all_targets.append(valid_t.cpu())

    inf_time = time.time() - start_time
    
    flat_preds = torch.cat(all_preds).numpy()
    flat_targets = torch.cat(all_targets).numpy()
    
    valid_pixels = len(flat_preds)
    
    # Calculate Diagnostics
    pred_min, pred_max = float(flat_preds.min()), float(flat_preds.max())
    target_min, target_max = float(flat_targets.min()), float(flat_targets.max())
    pred_mean = float(flat_preds.mean())
    target_mean = float(flat_targets.mean())
    
    # Raw Uncalibrated Metrics
    # Note: Scientifically invalid to interpret MAE/RMSE directly for performance, 
    # but reported as diagnostic.
    mae = float(np.mean(np.abs(flat_preds - flat_targets)))
    rmse = float(np.sqrt(np.mean((flat_preds - flat_targets)**2)))
    
    # Pearson Correlation (Scale/Shift Invariant, highly valid metric for zero-shot uncalibrated)
    p_mean = flat_preds.mean()
    t_mean = flat_targets.mean()
    cov = np.sum((flat_preds - p_mean) * (flat_targets - t_mean))
    p_var = np.sqrt(np.sum((flat_preds - p_mean)**2))
    t_var = np.sqrt(np.sum((flat_targets - t_mean)**2))
    corr = float(cov / (p_var * t_var)) if (p_var * t_var) > 0 else 0.0
    
    results = {
        "protocol": "Strict Zero-Shot (No Affine Fit)",
        "samples": test_samples,
        "valid_pixels": valid_pixels,
        "inference_time_s": round(inf_time, 2),
        "prediction_range": [round(pred_min, 4), round(pred_max, 4)],
        "target_range": [round(target_min, 4), round(target_max, 4)],
        "prediction_mean": round(pred_mean, 4),
        "target_mean": round(target_mean, 4),
        "raw_mae_m": round(mae, 4),
        "raw_rmse_m": round(rmse, 4),
        "pearson_correlation": round(corr, 4)
    }
    
    out_dir = Path("experiments/phase10/metrics")
    log_dir = Path("experiments/phase10/logs")
    out_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    
    with open(out_dir / "gamus_to_potsdam_zero_shot.json", "w") as f:
        json.dump(results, f, indent=2)
        
    with open(log_dir / "gamus_to_potsdam_zero_shot.log", "w") as f:
        f.write("GAMUS -> Potsdam Zero-Shot Log\n")
        f.write(json.dumps(results, indent=2) + "\n")
        
    print(json.dumps(results, indent=2))
    print("\nEvaluation Complete.")

if __name__ == "__main__":
    main()
