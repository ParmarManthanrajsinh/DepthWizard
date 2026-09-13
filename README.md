# DepthWizard · Single-View Height Estimation & 3D Flythrough
### ISRO SAC · Smart India Hackathon (Problem Statement SIH26175)

DepthWizard turns a single 2D optical image (satellite or aerial, in PNG, JPG, or GeoTIFF format) into an accurate digital surface model (DSM) and lets users navigate the reconstructed 3D terrain in real time through an interactive flythrough.

Judging is split 50/50:
- **50% DSM Accuracy**: RMSE, MAE, and correlation vs. reference elevation data (SRTM-30m / GCPs).
- **50% 3D Visualization Quality**: Projection accuracy, navigability, standalone deployability, and UX.

---

## 🏛️ System Architecture

One monorepo, one deployable service — no separate backend/frontend hosts:

```text
                     ┌─────────────────────────────────────────────┐
                     │            ONE FastAPI process              │
                     │                                             │
  Browser  ───────▶  │  ┌───────────────┐   ┌──────────────────┐   │
                     │  │ htmx + Jinja2 │   │ Elevation Pipeline │ │
                     │  │ upload/job UI │──▶│ (depth model,    │ │
                     │  │               │   │  scale calib.,   │ │
                     │  └───────────────┘   │  mesh export)    │ │
                     │          │           └──────────────────┘ │
                     │          │                     │            │
                     │          ▼                     ▼            │
                     │  ┌───────────────┐   ┌──────────────────┐   │
                     │  │ static/viewer/│   │  job metadata    │   │
                     │  │ raylib→WASM   │   │  (SQLite)        │   │
                     │  │ (C++20/WebGL2)│   └──────────────────┘   │
                     │  └───────────────┘                          │
                     └─────────────────────────────────────────────┘
```

---

## 👥 Team Roles & Module Ownership

| Role | Module | Primary Ownership & Files |
|---|---|---|
| **ML/Elevation Lead** | Module 1 | Depth model (`app/pipeline/estimator.py`), PyTorch/transformers inference |
| **Geospatial Lead** | Module 1 | GDAL/rasterio GeoTIFF I/O (`app/pipeline/geospatial.py`), SRTM-30m calibration (`app/pipeline/calibration.py`) |
| **Mesh/Graphics Bridge** | Module 2 | Heightfield triangulation, decimation, and GLB/OBJ packaging (`app/pipeline/mesh_builder.py`) |
| **Engine/Rendering Lead** | Module 3 | Raylib C++ flythrough viewer & Emscripten WASM build (`engine/`) |
| **Full-Stack/Integration** | Module 4 | FastAPI routes, Jinja2/htmx UI, SQLite DB, Docker (`app/routes/`, `app/templates/`) |
| **Pitch & Deliverables** | Docs/Demo | Technical documentation, demo script, benchmark slides |

---

## 📋 Implementation Progress & Roadmap (SIH26175 Track)

Progress tracked against the 50/50 judging split: **50% Metric DSM Accuracy** + **50% 3D Visualization & Flythrough Quality** (referenced from [`REPORT.md`](file:///e:/HackathonProjects/SIH/REPORT.md)).

### Current Progress (Completed)

- [x] **Module 1: Elevation Estimation & Geospatial Calibration**
  - [x] Pluggable depth architecture with `MockDepthEstimator` (offline/synthetic) & `DepthAnythingV2Estimator` (Hugging Face PyTorch).
  - [x] Normalization and depth-to-height inversion pipeline.
  - [x] GeoTIFF parsing via `rasterio` (CRS detection, affine geotransform, bounding box extraction).
  - [x] Least-squares affine scale/offset regression ($h_{metric} = a \cdot d_{rel} + b$) with RMSE, MAE, and Pearson correlation ($r$) statistics.
  - [x] Ground Control Points (GCPs) Survey Calibration: End-to-end support for sparse ground survey elevation points (CSV upload supporting pixel coordinates (x,y) or geographic (lat,lon) with least-squares scale/offset calibration).
  - [x] Dual output paths: Non-georeferenced relative rDSM vs. georeferenced metric DSM GeoTIFF export.
  - [x] Live DEM query & caching: Automatic fetching of SRTM-30m tiles via OpenTopography API (with `OPENTOPOGRAPHY_API_KEY` support), disk caching (`data/cache/dem/`), and explicit synthetic fallback warnings.
  - [x] 2D color-relief preview generation (`matplotlib.cm.terrain`).
  - [x] Synthetic sample benchmark generators (`sample_himalayas.tif`, `sample_crater.png`).

- [x] **Module 2: Heightmap to 3D Mesh Synthesis**
  - [x] Regular 2.5D heightfield triangulation grid algorithm.
  - [x] Smooth vertex normals derivation via adjacent triangle cross products.
  - [x] UV coordinate computation mapping original optical imagery onto 3D terrain surface.
  - [x] Adaptive Curvature & Gradient Mesh Decimation: Simplifies flat regions while preserving full resolution on ridges and cliffs.
  - [x] Standalone binary glTF (`.glb`) export with embedded textures and PBR materials.

- [x] **Module 3: Interactive 3D Flythrough**
  - [x] Native C++ Raylib WebAssembly 3D engine (`raylib_viewer.wasm` + `raylib_viewer.js`) compiled via EMSDK.
  - [x] Emscripten MEMFS mesh ingestion: direct streaming of `.glb` models from FastAPI into WASM VRAM.
  - [x] 6-DOF first-person flight camera (WASD lateral/forward, Space/C vertical, Shift 2.5x turbo boost, mouse drag look).
  - [x] Live aerospace telemetry HUD overlay (camera altitude, coordinate readouts, slope pitch, spatial CRS, engine state) bridged directly from C++ frame loop.
  - [x] Interactive mesh wireframe toggle mode (`X` key).
  - [x] Complete elimination of Three.js and all external CDN 3D libraries.
  - [x] Cross-platform build automation (`build_wasm.ps1`, `build_wasm.bat`, `build_wasm.sh`).

- [x] **Module 4: Web Orchestration & Interface**
  - [x] Single monorepo architecture: one FastAPI process, zero microservice sprawl.
  - [x] Server-driven reactive UI using HTMX & Jinja2 partials (`upload_form.html`, `job_status.html`, `job_result.html`).
  - [x] Real-time telemetry badges: Active depth model ("Depth Anything V2 [PyTorch]" vs "Mock Dev Mode") and calibration accuracy provenance ("Verified Ground Truth" vs "Synthetic Baseline").
  - [x] Async background worker execution queue with SQLite persistence via SQLAlchemy.
  - [x] Clean, aerospace telemetry design system locked in `design.md` with Hallmark anti-slop rules.
  - [x] Full test suite with automated pipeline, API, and WebAssembly viewer testing (`pytest tests -v`).

---

### Future Implementation (Remaining Roadmap)

- [ ] **Module 1: Elevation Pipeline Scaling & Ground Truthing**
  - [ ] **Satellite-Specific Model Tuning**: Benchmark fine-tuned ZoeDepth and satellite-specialized Depth Anything checkpoints.
  - [ ] **Large Scene Tiling**: Cloud Optimized GeoTIFF (COG) windowed reading and chunked inference for gigabyte-scale scenes.

- [ ] **Module 2: Advanced Mesh & Polygon Optimization**
  - [ ] **Adaptive Quadric Error Metric (QEM) Decimation**: Dynamic Level of Detail (LOD) polygon reduction to sustain 60 FPS on lower-end devices.
  - [ ] **Normal Map Baking**: High-to-low poly normal map baking to retain micro-surface detail without polygon overhead.
  - [ ] **Multi-Format Export**: Alternative packaging for Wavefront OBJ + MTL bundles alongside single-file `.glb`.

- [ ] **Module 3: Enhanced Flight Simulation & Topographic Shaders**
  - [ ] **Cinematic Flight Paths**: Waypoint-based automated flythrough tours and camera trajectory replay for jury demonstrations.
  - [ ] **Topographic Shader Effects**: Real-time contour lines and dynamic sun-angle directional hillshading in fragment shader.
  - [ ] **Slope Hazard Heatmap**: Visual color-coded slope overlay to assist disaster and terrain risk assessment.

- [ ] **Module 4: Benchmarking & Demonstration Deliverables**
  - [ ] **Standardized Benchmark Script**: Automated batch evaluation against ISRO SAC test datasets reporting aggregate RMSE and MAE.
  - [ ] **Single-Container Cloud Deployment**: Push pre-built image to Docker Hub / deploy to public VPS / Fly.io for remote judges.
  - [ ] **Pitch & Deliverables Package**: Technical architecture presentation slides, jury demo script, and final report.

---

## ⚡ Quickstart (3 Steps)

### 1. Install Dependencies
Using Python 3.12:
```powershell
py -3.12 -m pip install -r requirements.txt
```

*(Optional ML dependencies: `pip install torch transformers rasterio` when working on GPU depth weights).*

### 2. Launch Development Server
```powershell
py -3.12 run.py
```

### 3. Open in Browser
Visit **`http://localhost:8000/`**.
- Click **"🏔️ Himalayan Alpine Valley"** or **"🪐 Impact Crater"** for instant 1-click test runs.
- Click **"Launch 3D Flythrough"** to fly over the reconstructed 3D terrain!

---

## 📁 Repository Layout

```text
SIH/
├── app/
│   ├── main.py                   # FastAPI app factory, static mounts & lifespan
│   ├── config.py                 # Paths, settings, resolution configurations
│   ├── db/
│   │   ├── session.py            # SQLite engine & sessionmaker
│   │   └── models.py             # Job metadata SQLAlchemy model
│   ├── pipeline/
│   │   ├── estimator.py          # Depth Anything V2 + Mock fallback for dev
│   │   ├── geospatial.py         # GeoTIFF CRS inspection & DSM export
│   │   ├── calibration.py        # Least-squares scale/offset regression & RMSE
│   │   ├── mesh_builder.py       # Heightmap -> Triangulated GLB / OBJ mesh
│   │   └── runner.py             # Background pipeline executor
│   ├── routes/
│   │   ├── api.py                # REST endpoints (/api/jobs, /api/jobs/{id}/mesh)
│   │   └── pages.py              # HTML routes for htmx dashboard & viewer
│   ├── templates/
│   │   ├── base.html             # Common layout (Manifesto constructivist dark design)
│   │   ├── index.html            # Main dashboard & recent jobs table
│   │   ├── viewer.html           # Full-screen 3D flythrough page
│   │   └── partials/             # htmx dynamic polling components
│   └── static/
│       ├── css/style.css         # Manifesto responsive CSS design system
│       ├── js/app.js             # Drag-and-drop & htmx helpers
│       └── viewer/               # 3D Flythrough runtime (Raylib 6.0 WASM engine)
├── engine/                       # Module 3: Raylib / C++ Engine Source
│   ├── CMakeLists.txt            # Native desktop build
│   ├── build_wasm.bat            # Windows Emscripten compile script
│   ├── build_wasm.sh             # Linux/macOS Emscripten compile script
│   └── src/
│       ├── main.cpp              # Raylib viewer loop (WASM/Native)
│       ├── camera.cpp/h          # Free-fly first-person camera controller
│       └── terrain.cpp/h         # Terrain loading & elevation queries
├── data/
│   ├── samples/                  # Pre-packaged sample optical images
│   ├── uploads/                  # Raw user uploads
│   └── outputs/                  # Calibrated DSMs (.tif) and 3D meshes (.glb)
├── tests/
│   ├── test_pipeline.py          # Pipeline unit tests (depth, mesh, GLB)
│   └── test_api.py               # Integration tests for FastAPI endpoints
├── scripts/
│   └── generate_sample.py        # Synthetic test data generator
├── Dockerfile                    # Single-container deploy
├── requirements.txt              # Core python packages
├── run.py                        # Single-command launcher
└── REPORT.md                     # Full architectural report
```

---

## 🛠️ How to Iterate on Your Module

### Module 1: Elevation Pipeline (`app/pipeline/`)
- **Relative depth**: Located in [`app/pipeline/estimator.py`](file:///e:/HackathonProjects/SIH/app/pipeline/estimator.py). Set `USE_MOCK_MODEL=false` to use HuggingFace weights (`Depth-Anything-V2-Small-hf` or `ZoeDepth`).
- **Scale calibration**: Located in [`app/pipeline/calibration.py`](file:///e:/HackathonProjects/SIH/app/pipeline/calibration.py). Connect real OpenTopography or SRTM-30m tiles for georeferenced GeoTIFFs to compute benchmark RMSE and MAE against ground truth.

### Module 2: Heightmap to Mesh (`app/pipeline/mesh_builder.py`)
- Takes 2D array and source RGB image.
- Uses [`generate_terrain_mesh()`](file:///e:/HackathonProjects/SIH/app/pipeline/mesh_builder.py) to triangulate and compute smooth vertex normals.
- [`export_pure_glb()`](file:///e:/HackathonProjects/SIH/app/pipeline/mesh_builder.py) writes self-contained binary glTF with embedded UV-mapped image texture. Adjust `MESH_GRID_RESOLUTION` in `app/config.py` to balance polygon density with 60 FPS flight speed.

### Module 3: Raylib Flythrough (`engine/`)
- **Native compilation**:
  ```powershell
  cd engine
  cmake -B build
  cmake --build build --config Release
  ```
- **WebAssembly compilation**:
  With EMSDK activated:
  ```powershell
  cd engine
  .\build_wasm.bat    # or ./build_wasm.sh on Unix
  ```
  This compiles directly into `app/static/viewer/raylib_viewer.wasm`.
- Standalone WebAssembly: Raylib 6.0 engine compiles directly to `app/static/viewer/raylib_viewer.js` and `.wasm`. Pre-compiled binaries are bundled in the repository for zero-setup execution.

### Module 4: UI & API (`app/templates/`, `app/routes/`)
- Uses **htmx**: No Node.js build step needed. Forms submit via `hx-post="/api/jobs"`, and progress updates via polling `hx-get="/jobs/{id}/status"`.
- All CSS styles live in [`app/static/css/style.css`](file:///e:/HackathonProjects/SIH/app/static/css/style.css).

---

---

## 📊 Benchmark Evaluation & Metric Verification (Held-Out Test Set)

DepthWizard evaluates monocular height estimation on the official **ISPRS Potsdam RGB + DSM Benchmark** across **150 held-out test crops** ($39,321,600$ valid evaluated pixels across $6$ distinct tiles: `2_11`, `3_12`, `3_13`, `4_14`, `4_15`, `5_11`).

### Honest Dual Protocol Benchmark

To prevent test-set data snooping, DepthWizard strictly separates evaluation into two transparent protocols:
1. **Honest Frozen Global Calibration (Primary / Real-World Deployment)**: Single affine scale ($a = 9.8105$) and offset ($b = 33.7337\text{ m}$) fitted strictly on the pooled validation split ($750,000$ pixels across 150 validation crops). At test time, zero ground-truth elevation is accessed.
2. **Oracle Upper Bound (Theoretical Limit)**: Affine scale and offset fit per test crop against its reference DEM. Represents the maximum geometric correlation ceiling attainable by the monocular representation.

### Comprehensive Benchmark Metrics:

The **Frozen Global Calibration** column is the headline deployment metric: a single affine $(a, b)$ fitted on the validation split and applied unchanged to every test crop — no test-time ground truth is accessed. The **Oracle** column fits the affine per test crop against its reference DEM; it is a diagnostic showing the ceiling of a purely affine correction of this relative representation, **not** an achievable deployment accuracy.

| Metric | **Honest Frozen Global Calibration (Deployment)** | Oracle Affine Fit (Diagnostic Ceiling) |
|---|---|---|
| **MAE (Mean Absolute Error)** | **$4.0702\text{ m}$** | $1.5756\text{ m}$ |
| **RMSE (Root Mean Square Error)** | **$4.6302\text{ m}$** | $2.2035\text{ m}$ |
| **Pearson Correlation ($r$)** | **$+0.6469$** | $+0.6469$ |
| **AbsRel (Relative Error)** | **$0.1042$** | $0.0409$ |
| **$\delta_1 (< 1.25)$** | **$0.9298$ ($93.0\%$)** | $0.9820$ ($98.2\%$) |
| **$\delta_2 (< 1.25^2)$** | **$0.9994$ ($99.9\%$)** | $0.9997$ ($100.0\%$) |
| **$\delta_3 (< 1.25^3)$** | **$1.0000$ ($100.0\%$)** | $1.0000$ ($100.0\%$) |

### Multi-Biome Performance Breakdown:

| Biome | Dataset | Test Crops | Valid Pixels | Honest MAE | Oracle MAE | Pearson $r$ |
|---|---|---|---|---|---|---|
| **Urban / Dense Built** | ISPRS Potsdam | 150 | $39,321,600$ | **$4.07\text{ m}$** | **$1.58\text{ m}$** | **$+0.647$** |
| **Residential / Suburban** | ISPRS Vaihingen | preparation supported via `scripts/prepare_vaihingen_dataset.py` — evaluation pending |

> **Reproducibility:** benchmark artifacts (`results/evaluation.json`, `results/global_calibration.json`, `results/evaluation.csv`) are committed. Regenerate with `python -m ml.evaluate` after running the dataset preparation scripts below.

---

## ⚙️ Environment Variables Reference

Configure environment parameters in `.env` (template in `.env.example`):

| Variable | Default | Description |
|---|---|---|
| `DEVICE` | Auto (`cuda` / `cpu`) | Compute device for depth inference and fine-tuning |
| `CKPT_PATH` | `results/best_checkpoint.pt` | Path to fine-tuned model checkpoint |
| `POTSDAM_ROOT` | `data/potsdam_raw` | Root directory containing extracted Potsdam tiles (`1_DSM/`, `2_Ortho_RGB/`) |
| `VAIHINGEN_ROOT` | `data/vaihingen_raw` | Root directory for ISPRS Vaihingen dataset |
| `DEFAULT_BATCH_SIZE` | `4` | Dataloader batch size for training |
| `OPENTOPOGRAPHY_API_KEY` | *(empty)* | Optional API key for live SRTM-30m tile queries |
| `PORT` | `8000` | Port for FastAPI web server |

---

## 🏋️ Model Training & Fine-Tuning Pipeline

DepthWizard includes an end-to-end fine-tuning pipeline (`ml/train.py`) tailored for remote sensing elevation:
- **Frozen DINOv2 Encoder**: 22M parameters frozen; only the 2.7M-parameter DPT depth head and neck are updated.
- **Scale-Shift Invariant + Multi-Scale Gradient Loss**: Exact scale-shift invariant loss ($\mathcal{L}_{ssi}$) combined with edge gradient matching ($\mathcal{L}_{grad}$).
- **Geospatial Augmentations**: Random flips and 90-degree rotations preserving exact spatial alignment.
- **8GB VRAM Optimization (RTX 4080 / 4060)**: Native fp16 mixed-precision (`torch.amp.autocast`) and gradient accumulation for batch size 4–8 in < 3.5 GB VRAM.

### 1. Run Rapid CPU Smoke Test
```powershell
python -m ml.train --smoke-test --max-steps 5 --limit-batches 2
```

> **Fine-tuning status:** the end-to-end training pipeline is complete and smoke-tested (see `results/training_log.json`), but the current checkpoint comes from a short CPU smoke-run — the benchmark metrics above are driven by the **frozen pretrained Depth Anything V2 backbone + affine calibration**, not by fine-tuned weights. Full GPU fine-tuning is planned work.

### 2. Run Local GPU Fine-Tuning (RTX 4080 / 4060 8GB VRAM)
```powershell
python -m ml.train --epochs 5 --batch-size 4 --grad-accum 2 --lr 5e-5
```

### 3. Fit Frozen Global Affine Calibration
```powershell
python scripts/fit_global_calibration.py
```
*(Fits $h = a \cdot d_{rel} + b$ on the validation split and exports `results/global_calibration.json`)*

---

## 🧪 Testing & Verification Suite

### 1. Run Automated Test Suite
```powershell
pytest tests -v
```
*(Validates 28 unit tests: FastAPI endpoints, depth/mesh pipeline, GLB export, loss functions, ML preprocessing, and affine regressions)*

### 2. Run Comprehensive Held-Out Benchmark Evaluation
```powershell
python -m ml.evaluate
```
*(Evaluates all 150 held-out crops under both Frozen Global and Oracle Upper Bound protocols, writes `results/evaluation.json`, `results/evaluation.csv`, and visualizations)*

### 3. Run Dataset Sample Checks
```powershell
python scripts/test_dataset_samples.py
```

### 4. Run End-to-End Demo Verification
```powershell
python scripts/test_end_to_end.py
```
*(Validates HTTP endpoints, file upload, PyTorch inference, GeoTIFF DSM export, and binary glTF generation served to the Raylib WASM viewer)*

### 5. Launch Full Application Server
```powershell
python run.py --port 8000
```
Visit `http://localhost:8000`.

---

## 🚢 Docker Deployment

```powershell
docker build -t depthwizard .
docker run -p 8000:8000 depthwizard
```
Visit `http://localhost:8000`.
