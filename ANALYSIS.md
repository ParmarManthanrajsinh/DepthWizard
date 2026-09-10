Read URL: https://github.com/IMG-PROCESS-SAC/SIH-DepthWizard-2026
Viewed content.md:1-300
Searched for "README.md"
Ran command: `git remote -v`
Read URL: https://raw.githubusercontent.com/IMG-PROCESS-SAC/SIH-DepthWizard-2026/main/README.md
Viewed content.md:1-31
Ran command: `git ls-remote https://github.com/IMG-PROCESS-SAC/SIH-DepthWizard-2026.git`
Ran command: `git fetch https://github.com/IMG-PROCESS-SAC/SIH-DepthWizard-2026.git main`
Ran command: `git ls-tree -r FETCH_HEAD`
Ran command: `git show FETCH_HEAD:README.md`
Viewed mesh_builder.py:1-100
Viewed mesh_builder.py:170-300
Viewed REPORT.md:1-182
Ran command: `Get-ChildItem -Path . -Filter "Docker*" -File`
Viewed Dockerfile:1-25
Listed directory scripts
Viewed generate_sample.py:1-100

# DepthWizard — Problem Statement Analysis & Implementation Roadmap
**Reference:** [IMG-PROCESS-SAC/SIH-DepthWizard-2026](https://github.com/IMG-PROCESS-SAC/SIH-DepthWizard-2026) · **Problem Statement ID: 26175**  
**Core Mission:** Single-View Height Estimation and 3D Flythrough (ISRO Space Applications Centre)

---

## 1. Problem Statement Requirements Breakdown

Judging is split **50% / 50%**:

| Criterion | Weight | Official Focus Areas |
|---|---|---|
| **DSM Metric Accuracy** | **50%** | RMSE, MAE, Pearson correlation vs reference LiDAR / DEM (SRTM-30m). Must prove stability across **4 distinct landscape biomes**: **Urban, Sparse, Hilly, Forested**. |
| **3D Rendering & UX** | **50%** | **Optical texture projection** onto 3D mesh, visual fidelity, first-person flight navigability, **structural height analysis**, **slope assessment**, and standalone deployability. |

### Dual Input Mode Contract
1. **Non-Georeferenced (PNG / JPG)**: Output **Relative Digital Surface Model (rDSM)** — dimensionless relative height profile used directly for 3D navigation.
2. **Georeferenced (GeoTIFF)**: Output **Absolute Metric DSM** — calibrated via SRTM-30m or sparse Ground Control Points (GCPs) in standard WGS84 GeoTIFF format.

---

## 2. Gap Analysis: What Is Actually Missing in DepthWizard

Comparing the live repository with the official ISRO specification reveals **6 key missing gaps**:

```
[Official ISRO PS ID: 26175]                   [DepthWizard Current State]
├── Optical RGB Texture Projection ─────────▶ ❌ Shader renders blue-gray gradient; ignores optical photo
├── Structural Height & Slope Analysis ─────▶ ❌ Has altitude readout, but no point Δh measurement or slope heatmap
├── 4-Biome Stability (Urban/Sparse/Hilly/Forest) ▶ ⚠️ Only 2 test samples (Himalayas & Crater)
├── GAMUS Dataset Benchmark Suite ──────────▶ ❌ No automated batch evaluation script reporting aggregate RMSE/MAE
├── rDSM vs Metric DSM UI Distinction ──────▶ ⚠️ Labels both as "DSM"; doesn't show rDSM vs DSM distinction
└── Standalone & Single-Container Deploy ───▶ ⚠️ Dockerfile present but lacks multi-stage optimization & test CI
```

---

### Gap 1: Optical RGB Texture Draping in 3D Engine *(CRITICAL VISUAL GAP)*
- **Requirement:** *"After computing the elevation map, project the original optical image onto the generated 3D terrain mesh."*
- **What's Missing:** `mesh_builder.py` bundles the JPEG satellite image into the GLB buffer as `baseColorTexture`. However, in [`engine/src/terrain.cpp`](file:///e:/HackathonProjects/SIH/engine/src/terrain.cpp), shader `kTerrainVS` / `kTerrainFS` overrides the texture with a synthetic 3-tone blue-gray gradient (`lowColor`, `midColor`, `highColor`), masking the actual satellite photo.
- **Fix Required:** Update `terrain.cpp` shader to sample `texture0` (`fragTexCoord`), and add a 3-way rendering toggle:
  1. `Optical RGB Texture` (Satellite image projected on 3D geometry).
  2. `Hillshade Shading` (Directional relief with contour shading).
  3. `Signal Red Wireframe` (Inspection mode).

---

### Gap 2: Structural Height Analysis & Slope Assessment *(CORE JUDGING CRITERION)*
- **Requirement:** *"Support seamless first-person navigation, structural height analysis, and slope assessment from arbitrary aerial perspectives."*
- **What's Missing:** The viewer displays camera altitude in HUD, but has no tools to:
  1. Inspect point elevation or measure relative height difference $\Delta h$ between terrain features (e.g., building height, cliff drop, crater depth).
  2. Compute and visualize terrain slope angles $\theta = \arctan(\sqrt{(\partial z/\partial x)^2 + (\partial z/\partial y)^2})$.
- **Fix Required:**
  - Add ray-to-terrain inspection in WASM / JS (`Click to inspect elevation`).
  - Calculate surface slope map in Python pipeline and provide a slope-angle color-ramp toggle in the flythrough HUD.

---

### Gap 3: 4-Biome Benchmark Suite (Urban, Sparse, Hilly, Forested)
- **Requirement:** *"Must demonstrate performance stability across urban, sparse, hilly, and forested landscapes."*
- **What's Missing:**
  - We currently only have 2 sample datasets (`sample_himalayas.tif` and `sample_crater.png`).
  - Missing synthetic/real representative test samples for **Urban** (sharp building edges) and **Forested** (dense canopy surface elevation).
  - No automated script exists to benchmark all 4 biomes in a single batch.
- **Fix Required:**
  - Expand `scripts/generate_sample.py` with `sample_urban.tif` and `sample_forested.tif` with georeferencing and paired reference elevations.
  - Create `scripts/benchmark.py` calculating aggregate RMSE, MAE, and Pearson $r$ across all 4 biomes.

---

### Gap 4: GAMUS Dataset Pipeline & Domain Gap Adaptation
- **Requirement:** *"Recommended Dataset: GAMUS (Earthflow on Hugging Face)... Use this data to overcome the domain gap between natural egocentric imagery and top-down remote sensing imagery."*
- **What's Missing:**
  - Depth Anything V2 is loaded directly from HuggingFace, but no documentation or utility exists showing how GAMUS remote-sensing depth pairs are utilized or evaluated.
- **Fix Required:**
  - Add `scripts/download_gamus.py` (or eval script) capable of pulling sample pairs from Hugging Face `earthflow/GAMUS`.
  - Include zero-shot evaluation pipeline that benchmarks Depth Anything V2 against GAMUS validation pairs.

---

### Gap 5: Strict rDSM vs Metric DSM Pipeline Separation
- **Requirement:**
  - Non-georeferenced → **rDSM** (dimensionless relative height).
  - Georeferenced → **Absolute DSM** (calibrated metric meters via SRTM/GCP).
- **What's Missing:**
  - Both downloads are currently labeled "DSM" in the UI.
- **Fix Required:**
  - For non-georeferenced images: Label output file `_rdsm.png` and `_rdsm.tif`, badge UI with `"rDSM (Relative Digital Surface Model)"`.
  - For georeferenced images: Label output `_dsm.tif` with `"Absolute Metric DSM (SRTM-30m Calibrated)"` and show verified RMSE/MAE badges.

---

### Gap 6: Single-Container Deployment & Jury Deliverables
- **Requirement:** Single container cloud deployment and complete jury demonstration package.
- **What's Missing:**
  - Docker multi-stage build verifying pre-compiled WASM static files.
  - Jury demo cheat-sheet and architecture slide deck for presentation.
- **Fix Required:**
  - Production `Dockerfile` with GDAL/PyTorch CPU wheel optimizations.
  - `docs/JURY_DEMO_SCRIPT.md` (3-minute winning presentation flow) and `docs/BENCHMARK_REPORT.md`.

---

## 3. Implementation Roadmap

```
  PHASE 1: Optical Texture Projection & Flythrough Shading (Visual Fidelity)
  ├── 1.1 Update terrain.cpp shader to sample baseColorTexture (Optical RGB satellite drape)
  ├── 1.2 Add 3-way toggle: RGB Texture / Hillshade / Wireframe (Hotkeys: T, H, X)
  └── 1.3 Recompile Raylib WASM engine and verify in browser at 60 FPS

  PHASE 2: Structural Height & Slope Assessment (Module 3 Features)
  ├── 2.1 Add terrain slope raster generation (Sobel/Horn slope gradient in Python)
  ├── 2.2 Add interactive elevation probe and Δh delta measurement in viewer HUD
  └── 2.3 Expose real-time surface slope angle under camera position

  PHASE 3: 4-Biome Benchmark & Evaluation Suite (50% Accuracy Criterion)
  ├── 3.1 Create sample_urban.tif and sample_forested.tif with reference ground truth
  ├── 3.2 Implement scripts/benchmark.py: batch runs Urban, Sparse, Hilly, Forested
  └── 3.3 Output standardized validation report table: RMSE, MAE, Pearson r per biome

  PHASE 4: GAMUS Dataset Integration & rDSM/DSM UX Polish
  ├── 4.1 Add GAMUS dataset evaluation utility in scripts/gamus_eval.py
  ├── 4.2 Explicit UI badge and export naming: rDSM (relative) vs DSM (metric)
  └── 4.3 Update upload form with explicit Biome tagging (Urban/Sparse/Hilly/Forested)

  PHASE 5: Packaging, Containerization & Jury Deliverables
  ├── 5.1 Finalize Dockerfile & test single-container startup
  ├── 5.2 Create docs/JURY_DEMO_SCRIPT.md (step-by-step 3-min winning pitch)
  └── 5.3 Run full test suite: pytest tests -v
```

---

## 4. Next Step Recommendation

Begin with **Phase 1 (Optical Texture Projection)**:
1. Update [`engine/src/terrain.cpp`](file:///e:/HackathonProjects/SIH/engine/src/terrain.cpp) to sample the embedded texture so satellite imagery directly drapes over the 3D terrain.
2. Recompile WASM via `build_wasm.ps1` and verify live in the browser.