# EX05_BASELINE.md

**Current Baseline Checkpoint**: `results/checkpoints/best_gamus_exp03b.pt`
**Model Architecture**: Depth Anything V2 Small + LoRA (r=8, alpha=16) + Trainable DPT Neck + MetricRegressionHead.
**Dataset Split**: 25 training scenes, 7 validation scenes, 6 isolated test scenes.
**Image Resolution**: 518x518 patches extracted from 1024x1024 scenes.
**Optimizer**: AdamW (weight_decay=0.01)
**Loss**: HeightAwareMetricLoss (Masked L1 + Smooth L1 + Grad) with weights [1.0, 1.0, 1.5, 2.0, 2.5, 3.0]
**Training Configuration (Exp 03B)**: 
- Learning Rate: Neck=1e-5, Head=1e-4
- Batch Size: 4 (with Gradient Accumulation = 2, Effective Batch Size = 8)
- Epochs: 20 max

**Exact Quantitative Baseline Metrics (Experiment 03B)**
(From `reports/experiment_03b_report.md`):
- **Test MAE**: 1.860 m
- **Test RMSE**: 3.839 m
- **Pearson r (Correlation)**: 0.8421
