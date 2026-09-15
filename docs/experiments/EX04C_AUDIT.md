# EX04C_AUDIT.md

## Pipeline Insertion Point Audit

### 1. Current Depth Representation
- **Format**: float32 numpy ndarray, shape `(H, W)` — typically `(1024, 1024)`
- **Units**: Metric AGL (Above Ground Level) in meters
- **Range**: Typically 0–40m, with occasional spikes to 150m
- **Source**: `DepthWizard03BEstimator.estimate()` in `app/pipeline/estimator.py`

### 2. Current Height Representation
- After EX04A conditioning: float32 ndarray, same spatial shape
- Height range compressed (gamma + percentile clip), gradients bounded
- After SRTM calibration: absolute ASL elevation (AGL + DEM baseline)

### 3. Safe Insertion Point for Multi-Scale Prior
The EX04C module slots in **between raw depth inference and EX04A**:

```
estimator.estimate(rgb_img)   →   metric_agl           (raw float32 AGL)
                                      ↓
                              EX04C terrain prior        ← INSERT HERE
                                      ↓
                              apply_ex04a_conditioning   (unchanged)
                                      ↓
                              calibrate_elevation        (SRTM + AGL)
```

This is the same slot where EX04B was inserted (runner.py line 63–69).
EX04C transforms the raw AGL array in-place before EX04A processes it.

### 4. How EX04A Remains Unchanged
- EX04A's `apply_ex04a_conditioning()` signature is `(depth_map, config) → (result, stats)`
- It does not know or care what preprocessing occurred upstream
- EX04C produces a float32 ndarray of the same shape and AGL semantics
- EX04A's percentile clipping, gamma, median filter, gradient limiting all operate normally

### 5. Risks of Changing Physical Height Calibration
- The AGL values carry physical meaning (meters above ground)
- The SRTM calibration step adds `d_norm + ref` — if EX04C changes the
  AGL scale, the resulting ASL elevation will be wrong
- **Mitigation**: EX04C must preserve the mean and variance of the AGL signal
  at the low-frequency level; it should only redistribute energy between
  spatial frequency bands, not change the overall magnitude
