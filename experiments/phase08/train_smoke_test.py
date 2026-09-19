import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import torch
from torch.utils.data import DataLoader
from transformers import AutoModelForDepthEstimation
from ml.datasets.gamus_dataset import GAMUSDataset
from ml.losses import CombinedDepthLoss

def gamus_smoke_test():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}")
    
    # 1. Dataset & DataLoader
    dataset = GAMUSDataset("data/GAMUS/raw", split="train", target_size=(518, 518))
    loader = DataLoader(dataset, batch_size=2, shuffle=True, num_workers=0)
    
    # 2. Model
    model_name = "depth-anything/Depth-Anything-V2-Small-hf"
    print(f"Loading {model_name}...")
    model = AutoModelForDepthEstimation.from_pretrained(model_name).to(device)
    
    # Ensure backbone is frozen as per standard training protocol
    if hasattr(model, "backbone"):
        for param in model.backbone.parameters():
            param.requires_grad = False
            
    # 3. Loss & Optimizer
    criterion = CombinedDepthLoss()
    optimizer = torch.optim.AdamW(filter(lambda p: p.requires_grad, model.parameters()), lr=5e-5)
    
    # 4. Single Step Smoke Test
    batch = next(iter(loader))
    imgs = batch["image"].to(device)
    depths = batch["depth"].to(device)
    masks = batch["valid_mask"].to(device)
    
    print(f"\nForward Pass:")
    print(f"  Input RGB: {imgs.shape}, dtype: {imgs.dtype}")
    print(f"  Target Depth: {depths.shape}, dtype: {depths.dtype}")
    print(f"  Target Mask: {masks.shape}, dtype: {masks.dtype}")
    
    optimizer.zero_grad()
    
    outputs = model(imgs)
    pred_depth = outputs.predicted_depth
    
    if pred_depth.shape[-2:] != depths.shape[-2:]:
        pred_depth = torch.nn.functional.interpolate(
            pred_depth.unsqueeze(1),
            size=depths.shape[-2:],
            mode="bilinear",
            align_corners=False,
        ).squeeze(1)
        
    print(f"  Pred Depth: {pred_depth.shape}, dtype: {pred_depth.dtype}")
    
    # CombinedDepthLoss expects (B, 1, H, W) or (B, H, W)
    loss, l_ssi, l_grad = criterion(pred_depth, depths, masks)
    
    print(f"\nLoss:")
    print(f"  Total Loss: {loss.item():.4f}")
    print(f"  SSI Loss: {l_ssi.item():.4f}")
    print(f"  Grad Loss: {l_grad.item():.4f}")
    
    # Check for NaN/Inf
    assert torch.isfinite(loss), "Loss is not finite!"
    
    print("\nBackward Pass:")
    loss.backward()
    
    # Check gradients
    has_nan_grad = False
    for name, param in model.named_parameters():
        if param.requires_grad and param.grad is not None:
            if not torch.isfinite(param.grad).all():
                has_nan_grad = True
                print(f"  NaN gradient in {name}")
                
    assert not has_nan_grad, "NaN gradients detected!"
    print("  Gradients are finite.")
    
    print("\nOptimizer Step:")
    optimizer.step()
    print("  Optimizer updated parameters successfully.")
    
    print("\nGAMUS TRAINING SMOKE TEST: PASS")

if __name__ == "__main__":
    gamus_smoke_test()
