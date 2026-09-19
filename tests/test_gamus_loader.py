import pytest
import torch
from pathlib import Path
from ml.datasets.gamus_dataset import GAMUSDataset

def test_gamus_dataset_initialization():
    root_dir = Path("data/GAMUS/raw")
    if not (root_dir / "images" / "train").exists():
        pytest.skip("Local GAMUS sample data not found, skipping loader test.")
        
    dataset = GAMUSDataset(root_dir=str(root_dir), split="train", target_size=(518, 518))
    
    assert len(dataset) > 0, "Dataset should have found at least 1 sample."
    assert len(dataset.samples) == len(dataset)

def test_gamus_dataset_getitem():
    root_dir = Path("data/GAMUS/raw")
    if not (root_dir / "images" / "train").exists():
        pytest.skip("Local GAMUS sample data not found, skipping loader test.")
        
    dataset = GAMUSDataset(root_dir=str(root_dir), split="train", target_size=(518, 518))
    
    sample = dataset[0]
    
    # Check keys
    assert "image" in sample
    assert "depth" in sample
    assert "valid_mask" in sample
    
    # Check shapes
    assert sample["image"].shape == (3, 518, 518)
    assert sample["depth"].shape == (1, 518, 518)
    assert sample["valid_mask"].shape == (1, 518, 518)
    
    # Check datatypes
    assert sample["image"].dtype == torch.float32
    assert sample["depth"].dtype == torch.float32
    assert sample["valid_mask"].dtype == torch.bool
    
    # Check image ranges (since it's normalized with ImageNet stats, it won't be strictly [0, 1] anymore)
    # But we can check that it has finite values
    assert torch.isfinite(sample["image"]).all()
    
    # Check depth ranges
    assert torch.isfinite(sample["depth"]).all()
    
    # Valid mask should be False or True (it's boolean now)
    assert ((sample["valid_mask"] == False) | (sample["valid_mask"] == True)).all()
