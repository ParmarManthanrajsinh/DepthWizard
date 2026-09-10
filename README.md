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
  - [x] Dual output paths: Non-georeferenced relative rDSM vs. georeferenced metric DSM GeoTIFF export.
  - [x] Live DEM query & caching: Automatic fetching of SRTM-30m tiles via OpenTopography API with disk caching (`data/cache/dem/`) and coarse baseline fallback.
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
  - [x] Async background worker execution queue with SQLite persistence via SQLAlchemy.
  - [x] Clean, aerospace telemetry design system locked in `design.md` with Hallmark anti-slop rules.
  - [x] Full test suite with automated pipeline, API, and WebAssembly viewer testing (`pytest tests -v`).

---

### Future Implementation (Remaining Roadmap)

- [ ] **Module 1: Elevation Pipeline Scaling & Ground Truthing**
  - [ ] **Ground Control Points (GCPs)**: Support manual or CSV-based GCP entry for sub-pixel ground elevation calibration.
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

## 🧪 Testing

Run test suite:
```powershell
pytest tests -v
```

---

## 🚢 Docker Deployment

```powershell
docker build -t depthwizard .
docker run -p 8000:8000 depthwizard
```
Visit `http://localhost:8000`.
