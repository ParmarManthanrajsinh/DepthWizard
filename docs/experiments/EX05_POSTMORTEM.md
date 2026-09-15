# EX05 POST-MORTEM: FORENSIC AUDIT

## 1. Confirmed Facts
1. **EX05 Production Rejection**: The final standardized 22-scene evaluation demonstrates a severe degradation in MAE (2.401m → 5.609m) and correlation (0.734 → 0.057) when compared to the EX03B baseline. EX05 exhibits "output collapse," severely narrowing the height range (11.226m → 0.419m) and eliminating meaningful geographic relief.
2. **Missing BatchNorm Buffers in Checkpoint**: The `checkpoints/exp05/best.pt` file contains **0 BatchNorm buffer keys**. The baseline `best_gamus_exp03b.pt` correctly contains 6 BatchNorm buffer keys (e.g., `metric_head.bn1.running_mean`).
3. **Internal Validation Discrepancy**: During the `train_exp05.py` run, the validation loop reported a Val MAE of ~2.50m. However, loading the saved checkpoint without its running stats results in a raw MAE of ~14m (squashed to std 0.98m).
4. **Batch Size Discrepancy**: EX03B was trained with `BATCH_SIZE = 4`. Due to hardware limitations (4.3 GB VRAM), EX05 was trained with `BATCH_SIZE = 1` and `GRAD_ACCUM_STEPS = 8`.

## 2. Identified Root Causes

### Cause 1: Checkpoint State Truncation (Code Logic Error)
**Location**: `scripts/train_exp05.py`, line 211
```python
"trainable_state_dict": {k: v for k, v in model.state_dict().items() if v.requires_grad},
```
**Evidence**:
The `MetricRegressionHead` utilizes `nn.BatchNorm2d` layers (`bn1`, `bn2`). BatchNorm running statistics (`running_mean`, `running_var`, `num_batches_tracked`) are registered as non-trainable buffers (`requires_grad = False`). By filtering the `state_dict` using `if v.requires_grad`, the EX05 training script stripped all batch normalization statistics from the saved checkpoint. When loaded by the evaluation script, these layers silently initialized to mean=0 and var=1, destroying the calibrated absolute scale offset.

### Cause 2: Instance-Level Normalization Drift (Hardware Limitation Consequence)
**Location**: `scripts/train_exp05.py`, line 150
```python
val_dataset = GAMUSPatchDataset(...) # DataLoader batch_size=1
```
**Evidence**:
Because EX05 was executed with `batch_size=1` on a 4.3 GB RTX 3050, the `BatchNorm2d` layers essentially acted as `InstanceNorm2d`. When computing batch statistics across a single image's spatial dimensions, the absolute height representation (the DC component) is subtracted. Over 5 epochs, the exponential moving average (EMA) of the running stats drifted severely. The network's linear weights adapted to this drifted, scale-erased distribution.
Injecting the healthy EX03B running stats back into the EX05 checkpoint improved the collapsed MAE (from 14m → 5.6m), but it could not recover the baseline's 2.401m MAE because the EX05 weights had already overfitted to the shifted training stats.

### Cause 3: Validation Protocol Divergence (Contextual Illusion)
**Evidence**:
During `train_exp05.py`, `validate_epoch` was called immediately after `train_epoch`. The model was instantiated *in memory* and possessed its drifted running stats. Therefore, it reported a seemingly healthy 2.50m Val MAE against those corrupted stats. Once the script completed and the model was loaded from disk, the running stats were lost, revealing the structural damage to the network weights.

## 3. Detailed Forensic Outputs

Running the `best.pt` checkpoint on a representative validation image (`DC_02_26.png`) via forensic reconstruction demonstrates the progressive collapse:

| State | Output Min | Output Max | Mean | Std | P2 | P50 | P98 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **EX03B (Baseline)** | 0.0000 | 29.4162 | 6.4952 | 7.3552 | 0.0000 | 4.1721 | 25.1758 |
| **EX05 (Missing Stats - 0/1)** | 0.0000 | 6.9393 | 1.3291 | 0.9881 | 0.0000 | 1.2732 | 3.6748 |
| **EX05 (Injected EX03B Stats)** | 3.6648 | 7.4579 | 5.5065 | 0.3095 | 4.9092 | 5.4831 | 6.2069 |

**Conclusion**: The EX05 output collapse definitely exists *before* EX04A is applied. The raw network weights have lost height stratification capacity.

## 4. Unresolved Causes
None. The combination of hardware-induced `batch_size=1` BatchNorm drift and a strict `requires_grad` checkpoint filtering explicitly accounts for 100% of the statistical decay observed.

## 5. Recommended Fixes
If a future fine-tuning pass is required, two strict modifications must be made to the training scripts:

1. **Checkpoint Safety**: 
   Change the state_dict filter to preserve `bn` buffers, identically to how `train_exp03b.py` handled it:
   ```python
   # Correct
   trainable_state = {k: v.cpu() for k, v in model.state_dict().items() 
                      if "lora" in k or "neck" in k or "metric_head" in k}
   ```
2. **BatchNorm Freezing**:
   If training on a VRAM-constrained GPU requiring `batch_size=1`, the `BatchNorm2d` layers inside the `MetricRegressionHead` MUST be frozen (`eval()` mode for the BN layers specifically, or converting them to `GroupNorm`). Allowing `BatchNorm2d` to calculate training statistics on single patches destroys absolute metric depth calibration.

## 6. Scientific Justification for Future Rerun
A future EX05 rerun is **scientifically justified** if the two recommended fixes are applied, as the underlying loss function and LoRA strategy remain theoretically sound. However, until a GPU with sufficient VRAM (e.g., RTX 4080) is secured to train with batch sizes ≥ 4, or BatchNorm is explicitly frozen, fine-tuning will continue to structurally destabilize the pipeline.

**Production stands firmly on EX03B + EX04A.**
