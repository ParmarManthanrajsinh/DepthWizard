# EX05_DATA_AUDIT.md

**Dataset Audit: GAMUS**

**Structure & Input**:
- **Images**: 1024x1024 optical RGB `.png` imagery (`data/GAMUS/<split>/images/`)
- **Targets**: 1024x1024 AGL (Above Ground Level) heights in meters (`data/GAMUS/<split>/heights/`, `.tif`)
- **Normalization**: Standard ImageNet normalization for inputs. 
- **Missing/Invalid pixels**: Masked using `M = isfinite(Hgt) & (Hgt >= 0.0)`.

**Splits**:
- **Train**: Managed via `GAMUSPatchDataset` (extracts 518x518 crops). Includes 25 diverse scenes defined in manifest configs.
- **Validation**: 7 fixed scenes (`DC_02_26`, `DC_29_15`, `DC_45_37`, `PHL_6157`, `PHL_6323`, `PHL_6488`, `PHL_6664`).
- **Test**: 6 strictly isolated scenes (`PHL_3622`, `PHL_4652`, `PHL_3931`, `PHL_4231`, `DC_44_63`, `DC_03_26`). NEVER used in training.

**Augmentation**:
- Synchronized spatial augmentations (random flips and orthogonal rotations) applied to both RGB and AGL tensors to prevent memorization and preserve pixel-level alignment.

**Data Leakage Prevention**:
- Data splitting is strictly enforced by filename lists in the training script.
- The `is_training` flag correctly disables augmentations and handles 4-corner tiling for deterministic inference on validation/test sets.
