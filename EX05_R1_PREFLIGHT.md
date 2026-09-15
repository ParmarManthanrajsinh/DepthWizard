# EX05-R1 PRE-FLIGHT REPORT

## 1. Objective
Prepare for a scientifically sound rerun of Experiment 05 by strictly mitigating the `BatchNorm2d` drift and checkpointing truncation issues discovered during the EX05 post-mortem. This report documents the fixes, the explicit diagnostic verifications, and confirms the environment is ready for a safe fine-tuning run. No full training has been performed.

## 2. Exact Files Changed / Created
- `scripts/train_exp05_r1.py`: The newly hardened training script containing the explicit fixes.
- `scripts/test_checkpoint_roundtrip.py`: A new deterministic test script asserting absolute numerical equivalence across checkpoint save/loads.
- (EX03B and EX04A production pipelines were strictly untouched and preserved).

## 3. BatchNorm Layers and Chosen Mitigation
**Target Layers**: `model.metric_head.bn1` and `model.metric_head.bn2` (both `nn.BatchNorm2d`).
**Mitigation Strategy**: The safest and most theoretically sound approach for fine-tuning on a 4.3 GB VRAM limit (`batch_size=1`) is to **freeze the BatchNorm statistics**. 
- A custom recursive hook (`freeze_bn(model)`) is injected directly into the training loop immediately after `model.train()`. 
- This hook iterates over all `nn.BatchNorm2d` layers and explicitly calls `.eval()` on them.
- **Rationale**: This strictly prevents `running_mean` and `running_var` from updating via exponentially moving averages of single 518x518 patches, while still allowing PyTorch to calculate gradients for the affine weights (`gamma`/`beta`) if needed. The global absolute scale representations learned in EX03B are locked and protected.

## 4. Checkpoint Key Verification (Round-Trip Test)
A deterministic script (`scripts/test_checkpoint_roundtrip.py`) was executed to prove that the state dictionary now correctly captures all elements:
- It loaded a sample image, evaluated the base EX03B network, and saved a FULL un-filtered `model.state_dict()`.
- **Verification**: Assertions confirmed that the 4 critical BatchNorm buffer keys (`running_mean` and `running_var` for both layers) were successfully serialized to disk, successfully overriding the previous `requires_grad=True` filter that caused EX05 to fail.
- **Tolerance**: The checkpoint was reloaded into a randomly initialized network and re-evaluated on the same sample image. The `max difference` between the pre-save and post-load tensors was exactly `0.0`. The round-trip test passed perfectly.

## 5. Preprocessing Equivalence Check
The pre-flight audit explicitly ensured that the evaluation logic contained within `validate_epoch` precisely matches the offline evaluation scripts.
- During training, `val_dataset` is instantiated with `GAMUSPatchDataset(is_training=False, crops_per_scene=1)`.
- This strictly evaluates deterministic center crops or un-augmented full images matching the standardized EX03B offline protocol, eliminating the contextual illusion observed in EX05 where cropped inferences misaligned with full-scene validation inferences.

## 6. Smoke Test Results
A 2-batch smoke test was executed (`python scripts/train_exp05_r1.py --smoke`).
**Diagnostic Output:**
- `[BEFORE SMOKE] BN1 Running Mean: -0.2354, Running Var: 28.4426`
- `[AFTER SMOKE] BN1 Running Mean: -0.2354, Running Var: 28.4426`
**Result**: The statistics are mathematically frozen. The network executes the forward and backward passes without triggering NaN values and without corrupting the batch normalization state.

## 7. Conclusion: Is Full Training Justified?
**Yes.** The combination of full `state_dict` preservation and mathematically frozen `BatchNorm2d` layers perfectly insulates the architecture from the structural failures of EX05. The EX05-R1 training loop is now scientifically secure for deployment whenever an updated geometry or quantitative checkpoint is requested by the pipeline.
