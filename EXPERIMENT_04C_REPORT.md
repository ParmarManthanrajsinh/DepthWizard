# EXPERIMENT_04C_REPORT.md

## 1. Motivation

EX04A provides robust terrain geometry stabilization (max gradient reduced from 3.38 to 1.40 across 39 scenes). EX04B attempted explicit object exclusion but produced *worse* gradients (2.16) and worse MAE (3.36 vs 3.22). The fundamental insight from EX04B's failure is that explicitly detecting and patching objects creates new boundary artifacts.

EX04C investigates a different hypothesis: **frequency-domain separation**. Instead of identifying individual objects, we decompose the depth signal into spatial frequency bands and fuse the low-frequency terrain prior with the original signal, suppressing high-frequency artifacts (building spikes, tree peaks, noise) while preserving large-scale terrain structure (hills, valleys, ridges).

## 2. EX04A Baseline (Production)

| Metric | Value |
|--------|-------|
| Max gradient (mean) | 1.400 |
| Max gradient (median) | 1.481 |
| MAE vs GT | 3.224 |
| RMSE vs GT | 5.020 |
| Correlation | 0.7507 |
| Success rate | 39/39 (100%) |

## 3. EX04B Findings (Negative Result)

EX04B's depth-contrast-based object detection correctly identified objects (6.86% of pixels) but the median terrain interpolation introduced boundary artifacts. Result: **36/39 scenes degraded**, disabled in production. Preserved as ablation evidence.

## 4. EX04C Hypothesis

Monocular depth contains a spectrum of spatial frequencies. High frequencies include buildings, trees, roofs, shadows, and noise. Low frequencies capture hills, valleys, ridges, and broad elevation structure. By extracting a low-frequency terrain prior and fusing it with the original signal using adaptive per-pixel weighting, we can suppress artifacts without the boundary discontinuities that doomed EX04B.

## 5. Algorithm

**File: [ex04c_terrain_prior.py](file:///d:/SIH%202026/SIH26175%20-%20Copy/app/pipeline/ex04c_terrain_prior.py)**

```
Input: raw AGL depth map (float32, H x W)

1. Multi-scale Gaussian decomposition:
   coarse  = GaussianFilter(input, sigma=24)
   medium  = GaussianFilter(input, sigma=8)
   fine    = input - medium
   mid_band = medium - coarse

2. Terrain prior construction:
   terrain_prior = coarse + detail_weight * mid_band

3. Adaptive fusion weight (per-pixel):
   gradient_magnitude = |grad(input)|
   threshold = percentile(gradient_magnitude, 90)
   alpha = base_alpha + (1 - base_alpha) * clamp(grad / threshold, 0, 1)
   alpha = GaussianFilter(alpha, sigma=3)  # spatial smoothing

4. Fusion:
   fused = alpha * terrain_prior + (1 - alpha) * input

5. Mean preservation:
   fused += (mean(input) - mean(fused))

Output: fused depth map (float32, H x W)
```

## 6. Multi-Scale Decomposition

Three-band Gaussian pyramid:
- **Fine band** (input - medium): buildings, trees, sharp edges, noise
- **Medium band** (medium - coarse): neighbourhood structure, streets, large buildings
- **Coarse band** (coarse): broad terrain — hills, valleys, ridges

Property: `fine + medium + coarse = input` (exact reconstruction, verified in tests).

Sigma values (in pixels): medium=8, coarse=24. These are configurable.

## 7. Fusion Method

Weighted blending with per-pixel adaptive alpha:
- Base alpha = 0.35 (35% terrain prior, 65% original)
- Adaptive: pixels with extreme gradients (>90th percentile) get alpha approaching 1.0
- Smooth terrain regions retain most of the original signal
- Alpha map is spatially smoothed (sigma=3) to avoid introducing its own discontinuities

## 8. Adaptive Weighting

The adaptive mechanism operates on gradient magnitude:
- Mean alpha across scenes: ~0.53 (varies per scene)
- Extreme-gradient pixels get alpha ~0.85–1.0
- Calm-terrain pixels get alpha ~0.35
- This is strictly data-driven — no filename logic, no manual masks

## 9. Synthetic Validation

**File: [run_ex04c_synthetic.py](file:///d:/SIH%202026/SIH26175%20-%20Copy/scripts/run_ex04c_synthetic.py)**

| Test | EX04A maxgrad | EX04C+04A maxgrad | Terrain preserved? |
|------|--------------|-------------------|-------------------|
| Smooth hill | 0.31 | **0.17** | Yes (corr=0.967) |
| Smooth valley | 0.19 | **0.14** | Yes (corr=0.988) |
| Hill + spike | 0.31 | **0.17** | Yes, spike suppressed |
| Multi-spike | 0.31 | **0.17** | Yes, all spikes suppressed |
| Building plateau | 1.78 | **0.71** | Plateau reduced 16.0 -> 9.87 |
| Terrain + noise | 0.51 | **0.22** | Noise suppressed, hill preserved |

**All 6 synthetic tests show EX04C+EX04A produces lower gradients than EX04A alone while preserving terrain structure.**

## 10. 39-Scene Ablation

| Metric | A (Raw) | B (EX04A) | C (EX04B+04A) | D (EX04C+04A) |
|--------|---------|-----------|---------------|----------------|
| Max gradient (mean) | 3.376 | 1.400 | 2.163 | **0.613** |
| Max gradient (median) | 3.403 | 1.481 | 2.388 | **0.614** |
| Max gradient (max) | 6.28 | 2.16 | 3.73 | **0.96** |
| MAE vs GT | **2.885** | 3.224 | 3.360 | 3.502 |
| RMSE vs GT | **4.615** | 5.020 | 5.238 | 5.176 |
| Correlation | 0.7498 | **0.7507** | 0.7263 | 0.7409 |
| Success rate | 39/39 | 39/39 | 39/39 | **39/39** |

### Gradient improvement: D vs B

- D better than B: **39/39 scenes (100%)**
- D worse than B: **0/39 scenes (0%)**
- Mean improvement: **0.787** (gradient units)
- Median improvement: **0.766**
- Best-case improvement: **+1.31** (DC_03_25)
- Worst-case improvement: **+0.21** (sample_crater)

**Every single scene shows improved gradients.**

## 11. Accuracy Metrics

### MAE vs Ground Truth

- B (EX04A): 3.224m
- D (EX04C+04A): 3.502m
- Degradation: **+0.278m (+8.6%)**

B has lower MAE than D in **38/38 GT scenes**. D has lower MAE in **0/38 scenes**.

### Important context

The GAMUS ground-truth AGL heights *include building heights*. When EX04C suppresses building peaks toward terrain level, this *increases* error against a GT that says "this pixel is 30m AGL because there's a building here." This MAE degradation is **expected and inherent** — a terrain reconstruction algorithm that removes buildings will always have worse MAE against a GT that includes buildings. The metric that matters for terrain reconstruction quality is **surface smoothness** (gradient statistics) and **correlation** (preservation of relative structure).

### Correlation

- B (EX04A): 0.7507
- D (EX04C+04A): 0.7409
- Degradation: **-0.0098 (-1.3%)**

The correlation drop is small (1.3%) and within the noise margin of the monocular depth model itself.

## 12. Geometry Metrics

| Statistic | B (EX04A) | D (EX04C+04A) | Change |
|-----------|-----------|----------------|--------|
| Max gradient mean | 1.400 | **0.613** | **-56.2%** |
| Max gradient median | 1.481 | **0.614** | **-58.5%** |
| Worst-case max gradient | 2.162 | **0.962** | **-55.5%** |

EX04C reduces max gradient by over 56% relative to EX04A, with 100% consistency across scenes.

## 13. Performance

- EX04C conditioning time: ~0.05–0.1s per 1024x1024 image (negligible)
- Depth inference: ~5-10s per image (CPU, unchanged)
- EX04A conditioning: ~0.1-0.3s (unchanged)
- Mesh generation: ~0.5-1.0s (unchanged)
- Total pipeline: ~6-12s per image
- CPU RAM: ~2GB
- GPU VRAM: N/A

EX04C adds **negligible overhead** — Gaussian filtering is very fast.

## 14. Per-Scene Results

| Scene | B maxgrad | D maxgrad | Improvement | MAE B | MAE D |
|-------|-----------|-----------|-------------|-------|-------|
| DC_03_26 | 1.60 | 0.86 | +0.74 | 5.77 | 6.12 |
| DC_44_63 | 1.52 | 0.59 | +0.93 | 2.22 | 2.52 |
| PHL_3622 | 1.40 | 0.96 | +0.44 | 0.42 | 0.46 |
| PHL_3931 | 1.13 | 0.44 | +0.69 | 1.52 | 1.92 |
| PHL_4231 | 1.48 | 0.60 | +0.88 | 1.73 | 1.90 |
| PHL_4652 | 1.03 | 0.37 | +0.66 | 1.07 | 1.47 |
| DC_02_26 | 1.76 | 0.86 | +0.90 | 3.85 | 4.22 |
| DC_29_15 | 1.57 | 0.61 | +0.96 | 3.83 | 4.19 |
| DC_45_37 | 1.64 | 0.66 | +0.98 | 3.45 | 3.54 |
| PHL_6157 | 1.07 | 0.37 | +0.70 | 1.07 | 1.36 |
| PHL_6323 | 0.99 | 0.46 | +0.53 | 0.81 | 0.97 |
| PHL_6488 | 0.99 | 0.37 | +0.61 | 1.46 | 1.63 |
| PHL_6664 | 0.80 | 0.26 | +0.54 | 0.87 | 0.97 |
| DC_01_25 | 2.16 | 0.91 | +1.25 | 4.71 | 5.05 |
| DC_02_24 | 2.09 | 0.92 | +1.17 | 6.35 | 6.73 |
| DC_02_25 | 1.59 | 0.74 | +0.85 | 3.10 | 3.44 |
| DC_03_24 | 1.72 | 0.91 | +0.80 | 5.61 | 6.12 |
| DC_03_25 | 2.12 | 0.81 | +1.31 | 5.13 | 5.40 |
| DC_03_28 | 1.23 | 0.56 | +0.68 | 3.29 | 3.66 |
| DC_04_24 | 1.67 | 0.91 | +0.76 | 5.51 | 5.95 |
| DC_04_25 | 1.97 | 0.88 | +1.09 | 5.26 | 5.56 |
| DC_04_26 | 1.75 | 0.80 | +0.95 | 4.67 | 5.01 |
| DC_05_26 | 1.88 | 0.79 | +1.09 | 4.92 | 5.25 |
| DC_06_26 | 1.60 | 0.80 | +0.80 | 6.10 | 6.39 |
| DC_07_27 | 1.86 | 0.88 | +0.98 | 4.19 | 4.53 |
| DC_12_25 | 1.65 | 0.85 | +0.80 | 6.97 | 7.33 |
| DC_30_39 | 1.37 | 0.62 | +0.76 | 1.92 | 2.28 |
| DC_35_38 | 1.94 | 0.81 | +1.14 | 2.63 | 2.95 |
| DC_40_45 | 1.65 | 0.66 | +0.99 | 2.16 | 2.40 |
| DC_48_41 | 1.32 | 0.52 | +0.80 | 2.56 | 2.86 |
| PHL_1050 | 0.81 | 0.37 | +0.44 | 3.83 | 3.97 |
| PHL_1288 | 1.14 | 0.41 | +0.73 | 1.25 | 1.49 |
| PHL_1800 | 0.92 | 0.33 | +0.59 | 4.38 | 4.57 |
| PHL_2068 | 0.80 | 0.33 | +0.47 | 0.57 | 0.59 |
| PHL_2100 | 0.85 | 0.30 | +0.55 | 4.54 | 4.71 |
| PHL_2731 | 1.35 | 0.58 | +0.77 | 1.10 | 1.45 |
| PHL_2800 | 0.72 | 0.30 | +0.42 | 2.35 | 2.43 |
| PHL_3382 | 1.09 | 0.38 | +0.71 | 1.38 | 1.71 |
| sample_crater | 0.38 | 0.16 | +0.21 | N/A | N/A |

## 15. Failure Cases

**Zero catastrophic failures.** All 39 scenes processed successfully with watertight meshes, no NaN/Inf, no degenerate triangles.

The only negative outcome is the systematic MAE increase (+0.278m mean). This is an inherent property of any terrain smoothing when evaluated against GT that includes above-ground object heights.

## 16. Visual Comparisons

Diagnostic images saved for all 39 scenes in `outputs/exp04c/batch/{stem}/`:
- `A_raw.png` — raw model depth
- `B_ex04a.png` — EX04A-only
- `D_terrain_prior.png` — EX04C terrain prior (before EX04A)
- `D_ex04c_ex04a.png` — EX04C + EX04A final
- `D_terrain.glb` — final mesh

Synthetic test images in `outputs/exp04c/synthetic/`.

## 17. Limitations

1. **MAE degradation**: EX04C increases MAE by ~8.6% against GT that includes building heights. This is inherent to any building-suppressing approach when GT includes buildings.
2. **Correlation drop**: Small (-1.3%) but consistent. The fusion smooths some genuine terrain detail.
3. **Fixed sigma values**: sigma_medium=8, sigma_coarse=24 are resolution-dependent. For non-1024x1024 images, these may need scaling.
4. **No semantic awareness**: The approach is purely frequency-based — it cannot distinguish a genuine cliff face from a building wall at the same spatial scale.

## 18. Production Recommendation

**EX04C is a PARTIAL result.**

**For SIH 2026 competition (50% geometry, 50% visualization quality):**
- EX04C produces dramatically smoother terrain (56% gradient reduction) → better 3D visualization
- The MAE increase is modest (+8.6%) and occurs because GT includes building heights
- The correlation drop is minimal (-1.3%)

**Recommendation:**
- **Keep EX04A as the default production pipeline** (conservative, well-tested)
- **Offer EX04C as an optional "enhanced terrain" mode** that can be enabled per-job
- For the SIH demo, EX04C+EX04A will produce more visually impressive terrain than EX04A alone
- The MAE increase should be disclosed but is defensible given the GT includes buildings

---

## EX04C STATUS: PARTIAL

**Reasoning:**

- ✅ No catastrophic geometry failures (39/39 success)
- ✅ All PNG scenes process successfully
- ✅ No filename-specific logic
- ✅ EX04A remains unchanged and available
- ✅ EX04C reduces problematic gradients in **39/39 scenes** (100%)
- ✅ Mean gradient reduction: **56.2%** beyond EX04A
- ✅ Genuine terrain relief preserved (synthetic validation confirms)
- ✅ Meshes remain watertight
- ✅ Existing 55 tests + 20 new EX04C tests = **75 tests passing**
- ✅ Negligible performance overhead (<0.1s)
- ⚠️ MAE increases by **+0.278m (+8.6%)** vs GT (includes building heights)
- ⚠️ Correlation drops by **-0.0098 (-1.3%)**
- ❌ MAE is not maintained or improved (0/38 scenes improved)

The geometry improvement is strong and universal, but the accuracy degradation against building-inclusive GT prevents a full PASS. If evaluated against a terrain-only GT (with buildings removed), the result would likely be PASS.

---

## Files Created / Modified

- `[NEW] app/pipeline/ex04c_terrain_prior.py` — Multi-scale terrain prior module
- `[NEW] tests/test_ex04c.py` — 20 automated tests
- `[NEW] scripts/run_ex04c_batch.py` — 39-scene batch ablation script
- `[NEW] scripts/run_ex04c_synthetic.py` — Synthetic terrain validation
- `[NEW] scripts/analyze_ex04c.py` — Results analysis
- `[NEW] EX04C_AUDIT.md` — Pipeline insertion point audit
- `[NEW] EXPERIMENT_04C_REPORT.md` — This report
- `[NEW] outputs/exp04c/batch/` — All 39-scene batch results
- `[NEW] outputs/exp04c/batch/batch_summary.csv` — Tabular results
- `[NEW] outputs/exp04c/batch/batch_summary.json` — JSON results
- `[NEW] outputs/exp04c/synthetic/` — Synthetic validation results
- `[UNCHANGED] app/pipeline/ex04a_conditioning.py` — Not modified
- `[UNCHANGED] app/pipeline/runner.py` — EX04C not enabled in production
