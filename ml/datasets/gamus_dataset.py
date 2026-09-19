import os
from pathlib import Path
from typing import Optional, Tuple
import numpy as np
import h5py
import torch
from torch.utils.data import Dataset
import torchvision.transforms.functional as TF
import random

class GAMUSDataset(Dataset):
    """
    PyTorch Dataset loader for the Earthflow GAMUS dataset.
    Loads RGB images and corresponding AGL heights from HDF5 format.
    Lazily opens h5py File handles in __getitem__ to be multi-worker safe.
    """
    
    def __init__(self, root_dir: str, split: str = "train", target_size: Tuple[int, int] = (518, 518)):
        """
        Args:
            root_dir: Root directory of GAMUS dataset (e.g., 'data/GAMUS/raw')
            split: 'train', 'val', or 'test'
            target_size: Target image dimensions (H, W) for Depth Anything V2
        """
        self.root_dir = Path(root_dir)
        self.split = split
        self.target_size = target_size
        
        self.images_dir = self.root_dir / "images" / split
        self.heights_dir = self.root_dir / "heights" / split
        
        if not self.images_dir.exists() or not self.heights_dir.exists():
            raise FileNotFoundError(f"Missing GAMUS directories for split '{split}' at {self.root_dir}")
        
        self.samples = []
        for img_path in sorted(self.images_dir.glob("*_RGB.h5")):
            basename = img_path.name.replace("_RGB.h5", "")
            height_path = self.heights_dir / f"{basename}_AGL.h5"
            
            if height_path.exists():
                self.samples.append({
                    "rgb": str(img_path),
                    "height": str(height_path)
                })
        
        if len(self.samples) == 0:
            raise ValueError(f"No valid GAMUS RGB/AGL pairs found in {self.images_dir}")
            
        # ImageNet normalization used by DINOv2 / DepthAnythingV2
        self.mean = [0.485, 0.456, 0.406]
        self.std = [0.229, 0.224, 0.225]

    def __len__(self) -> int:
        return len(self.samples)
        
    def __getitem__(self, idx: int) -> dict:
        sample = self.samples[idx]
        
        # We must open h5py files locally inside __getitem__ to prevent
        # multi-processing deadlock or pickling errors across PyTorch workers.
        with h5py.File(sample["rgb"], "r") as f_rgb, \
             h5py.File(sample["height"], "r") as f_hgt:
             
            # Read into numpy arrays
            rgb_np = f_rgb["image"][()]  # (H, W, 3) uint8 [0, 255]
            hgt_np = f_hgt["image"][()]  # (H, W) float32
            
        # Convert to PyTorch tensors
        rgb = torch.from_numpy(rgb_np).permute(2, 0, 1).float() / 255.0  # (3, H, W) [0, 1]
        height = torch.from_numpy(hgt_np).unsqueeze(0).float()           # (1, H, W)
        
        # Spatial augmentation / resizing
        # Random crop for training, Center crop for validation/test
        h, w = rgb.shape[1], rgb.shape[2]
        th, tw = self.target_size
        
        if self.split == "train":
            # Random crop
            if h >= th and w >= tw:
                i = random.randint(0, h - th)
                j = random.randint(0, w - tw)
                rgb = TF.crop(rgb, i, j, th, tw)
                height = TF.crop(height, i, j, th, tw)
            else:
                rgb = TF.resize(rgb, [th, tw], antialias=True)
                height = TF.resize(height, [th, tw], antialias=True)
                
            # Random horizontal flip
            if random.random() > 0.5:
                rgb = TF.hflip(rgb)
                height = TF.hflip(height)
        else:
            # Center crop
            if h >= th and w >= tw:
                rgb = TF.center_crop(rgb, [th, tw])
                height = TF.center_crop(height, [th, tw])
            else:
                rgb = TF.resize(rgb, [th, tw], antialias=True)
                height = TF.resize(height, [th, tw], antialias=True)
                
        # Normalize RGB
        rgb = TF.normalize(rgb, self.mean, self.std)
        
        # Create a valid mask (filter out negative height values and NaNs)
        valid_mask = (height >= 0.0) & torch.isfinite(height)
        
        # Replace invalid values with 0.0 to prevent NaN propagation in loss calculation
        height = torch.where(valid_mask, height, torch.zeros_like(height))
        
        return {
            "image": rgb,          # (3, target_H, target_W)
            "depth": height,       # (1, target_H, target_W)
            "valid_mask": valid_mask # (1, target_H, target_W)
        }
