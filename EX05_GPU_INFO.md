# EX05_GPU_INFO.md

**Hardware Audit Results**

- **CUDA Available**: True
- **Device Name**: NVIDIA GeForce RTX 3050 A Laptop GPU
- **VRAM (GB)**: ~4.29 GB
- **PyTorch Version**: 2.6.0+cu124
- **AMP Support**: True

**WARNING**: The user prompt intended for an **NVIDIA RTX 4080**; however, the available hardware is an **RTX 3050 A Laptop GPU** with only 4.3 GB of VRAM.

**Mitigation Plan**:
Training on 4.3GB VRAM is highly restrictive for a ViT-based model (even with LoRA).
- The baseline batch size of 4 used in Exp03B will almost certainly cause a CUDA Out-of-Memory (OOM) error on this GPU.
- **Adjusted Configuration**: I will reduce the actual batch size to 1 or 2, and proportionally increase gradient accumulation (e.g., if batch_size=1, gradient_accumulation_steps=8) to preserve the effective batch size of 8.
- Automatic Mixed Precision (AMP) will be strictly utilized to save VRAM.
- `torch.backends.cudnn.benchmark = True` will be enabled if appropriate, but memory conservation is the absolute priority.
