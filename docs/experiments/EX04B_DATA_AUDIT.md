# EX04B_DATA_AUDIT.md

## Dataset / Label Audit for Experiment 04B

### GAMUS Dataset Structure

The GAMUS (Geo-referenced Aerial Metric Urban Scenes) dataset is the sole structured
image+height dataset in this repository. It contains paired 1024×1024 optical RGB PNGs
and single-band float32 AGL (Above Ground Level) height rasters in GeoTIFF format.

### Splits and Counts

| Split | RGB Images | Height Rasters | Paired |
|-------|-----------|---------------|--------|
| train | 24 | 24 | 24 |
| val   | 7  | 7  | 7  |
| test  | 6  | 6  | 6  |
| **Total** | **37** (+ 1 sample_crater + 1 raw) | **37** | **37** |

### Available Data per Scene

- **RGB**: 1024×1024 PNG, mode=RGB
- **Height**: 1024×1024 float32 GeoTIFF, single band
  - Values represent **AGL height in meters** (Above Ground Level)
  - Ground/terrain = ~0.0m
  - Buildings/trees = positive AGL (e.g. 10m–40m)
  - Some tiles have minimum = -5.0m (below grade / sub-surface features)
  - Max observed AGL: 151.4m (PHL_4652, likely a tall antenna/tower)

### Semantic Labels / Segmentation Masks

**NONE FOUND.**

- No `masks/`, `labels/`, `segments/`, `classes/` directories anywhere in `data/GAMUS/`
- No `*mask*`, `*label*`, `*seg*`, `*cls*`, `*lc*`, `*land*` files found
- No class-ID JSON or mapping files found
- No segmentation model code or imports found in `app/pipeline/` or `ml/`
- No segmentation-related Python dependencies in `requirements.txt`
- `data/GAMUS/processed/` is empty
- `data/GAMUS/raw/` contains mirrored raw height/image directories (no labels)

### Class/Label Mapping

Not applicable — no semantic labels exist in the dataset.

### Key Observation: AGL Height as Semantic Proxy

The AGL height rasters themselves encode a strong implicit semantic signal:

- **Ground/terrain**: AGL ≈ 0m (within ±1m)
- **Low vegetation / fences**: AGL ≈ 1–3m
- **Trees / tall vegetation**: AGL ≈ 5–15m
- **Buildings (1-3 stories)**: AGL ≈ 3–12m
- **Tall buildings (4+ stories)**: AGL ≈ 12–40m
- **Tall structures (towers)**: AGL > 40m

This means the ground-truth AGL rasters *can* serve as a reference for
understanding which pixels are above-ground objects, but only at training/
evaluation time — not at inference time on novel images.

### Inference-Time Semantic Information Available

At inference time (when a user uploads a new satellite PNG), we have:
1. The RGB image itself
2. The predicted AGL depth map from the model

We do **not** have:
- Ground-truth AGL
- Pre-computed segmentation masks
- Land-cover maps
- Building footprint vectors

### Conclusion for EX04B

Since no external segmentation model or labels exist in the project, EX04B must
derive object/terrain separation **purely from the predicted depth map and the
RGB image**. The approach will use:

1. **Local height contrast** in the predicted depth map to identify above-ground objects
2. **Morphological analysis** to clean up detected regions
3. **Surrounding terrain interpolation** to reconstruct underlying ground surface
4. Ground-truth AGL rasters for **ablation evaluation only** (not used in the inference pipeline)
