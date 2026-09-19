import sys
from pathlib import Path
import torch
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ml.train import train_model, evaluate_val_split
from ml.dataset import SatelliteElevationDataset
from transformers import AutoModelForDepthEstimation

def main():
    print("Starting Phase 10A Potsdam Controlled Fine-Tuning")
    out_dir = Path("experiments/phase10/checkpoints")
    log_dir = Path("experiments/phase10/logs")
    metrics_dir = Path("experiments/phase10/metrics")
    
    out_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    metrics_dir.mkdir(parents=True, exist_ok=True)
    
    best_ckpt = out_dir / "best_potsdam.pt"
    
    # Train model
    res = train_model(
        train_dir=Path("data/train"),
        val_dir=Path("data/validation"),
        epochs=3,  # Sufficient to show convergence
        batch_size=4,
        lr=5e-5,
        grad_accum_steps=2,
        output_checkpoint=best_ckpt,
        output_log=log_dir / "training.log"
    )
    
    print("\n--- Training Complete ---")
    print(f"Best Val MAE: {res['best_val_mae']:.4f}")
    
    print("\n--- Evaluating on Held-Out Test Set ---")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = AutoModelForDepthEstimation.from_pretrained("depth-anything/Depth-Anything-V2-Small-hf").to(device)
    
    checkpoint = torch.load(best_ckpt, map_location=device, weights_only=True)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    
    test_dataset = SatelliteElevationDataset(root_dir="data/test")
    test_metrics = evaluate_val_split(model, test_dataset, device=device, max_samples=9999, stride=1)
    
    print(f"Test MAE: {test_metrics['mae']:.4f} m")
    print(f"Test RMSE: {test_metrics['rmse']:.4f} m")
    print(f"Test Pearson r: {test_metrics['corr']:.4f}")
    
    import json
    with open(metrics_dir / "test_metrics.json", "w") as f:
        json.dump(test_metrics, f, indent=2)

if __name__ == "__main__":
    main()
