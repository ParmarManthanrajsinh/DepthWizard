# DepthWizard — Technical Architecture & Tech Stack Report
### SIH26175 · Single-View Height Estimation and 3D Flythrough · ISRO (Department of Space)

---

## 1. Problem Restated

Turn a single 2D optical image (satellite/aerial, PNG/JPG/GeoTIFF) into an elevation model, then let a user fly through the reconstructed terrain in real time. Two input modes are required:

- **Non-georeferenced imagery (PNG/JPG)** → Relative Digital Surface Model (rDSM)
- **Georeferenced imagery (GeoTIFF)** → Absolute DSM with metric heights, calibrated against a low-res DEM (e.g. SRTM-30m) or sparse Ground Control Points (GCPs)

Judging is split 50/50: **DSM accuracy** (RMSE/MAE/correlation vs. reference) and **visualization quality** (projection accuracy, navigability, standalone deployability, UX).

That 50/50 split is the key architectural signal — this is two products in one submission, and both halves need to be genuinely solid, not one polished half carrying a weak other half.

---

## 2. System Overview

**Deployment constraint driving this architecture:** one monorepo, one deployable service — no separate backend/frontend hosts, no hand-off between a hosted web app and a locally-run native binary. That single constraint is why Module 3 (the flythrough) is compiled to WebAssembly rather than shipped as a native executable — see Module 3 for the reasoning.

```
                     ┌─────────────────────────────────────────────┐
                     │            ONE FastAPI process                │
                     │                                               │
  Browser  ───────▶  │  ┌───────────────┐   ┌──────────────────┐    │
                     │  │ htmx + Jinja2  │   │ Elevation Pipeline │   │
                     │  │ upload/job UI  │──▶│ (depth model,      │   │
                     │  │                │   │  scale calib.,     │   │
                     │  └───────────────┘   │  mesh export)       │   │
                     │          │            └──────────────────┘   │
                     │          │                      │             │
                     │          ▼                      ▼             │
                     │  ┌───────────────┐   ┌──────────────────┐    │
                     │  │ static/viewer/ │   │  job metadata     │    │
                     │  │ raylib→WASM    │   │  (SQLite)         │    │
                     │  │ (.wasm/.js)    │   └──────────────────┘    │
                     │  └───────────────┘                            │
                     └─────────────────────────────────────────────┘
```

Everything — HTML pages, the depth-estimation API, and the compiled raylib flythrough viewer — is served by the same FastAPI process from the same repo. The browser loads the WASM viewer as a static asset and talks to the elevation API via plain `fetch()`, all same-origin. No second service, no process handoff, nothing to keep in sync across two deployments.

This mirrors the mock-first, module-boundary approach you already used on AgriShield: each piece can be stubbed and demoed in isolation before integration, even though they now ship as one artifact.

---

## 3. Module 1 — Elevation Estimation Pipeline

**Language:** Python (this is non-negotiable — every usable pretrained depth model ships as a PyTorch/HF checkpoint)

| Component | Tool | Why |
|---|---|---|
| Monocular depth backbone | **Depth Anything V2** (or ZoeDepth as fallback) via HuggingFace `transformers` | Best relative-depth generalization currently available pretrained; Depth Anything V2 also has a metric-depth fine-tuned variant which reduces your calibration burden |
| Inference serving | **FastAPI** | Same pattern as AgriShield's backend — you already know this stack cold, don't relearn one under time pressure |
| Geospatial I/O | **rasterio** + **GDAL** | Read/write GeoTIFF, extract CRS/geotransform metadata to detect georeferenced vs. non-georeferenced input |
| DEM reference data | **SRTM 30m** via `elevation` package or OpenTopography API | Ground truth for scale calibration on georeferenced inputs |
| Scale calibration | **NumPy / SciPy** least-squares fit | Regress relative depth values against SRTM elevations at sample points → converts scale-agnostic depth to metric height |
| Array/raster ops | **NumPy, OpenCV** | Resizing, normalization, edge cleanup on the depth map before mesh generation |

**Two clearly separated code paths** (build both — they're graded separately in the "DSM Estimation" criterion):
1. Non-georeferenced: raw model output → normalized relative height map → done.
2. Georeferenced: model output → sample SRTM at matching lat/lon → fit relative→absolute scale/offset → output real-unit DSM as GeoTIFF.

**Team-role note:** whoever handled AgriShield's FastAPI/data layer should own this module — it's the same shape of work (ingest → transform → structured output), just with rasters instead of tabular risk data.

---

## 4. Module 2 — Heightmap → 3D Mesh

This is the bridge between the ML pipeline and the renderer, and it's smaller than it looks — don't over-scope it.

| Component | Tool | Why |
|---|---|---|
| Heightfield → mesh | Custom Python (NumPy grid triangulation) or **Open3D** | A heightmap is just a regular grid — displace each vertex by its depth value, triangulate the grid. A few hundred lines, not a research problem |
| Mesh simplification | **Open3D** or `trimesh` decimation | Full-resolution satellite images can produce huge meshes; decimate for real-time flythrough framerate |
| Export format | **glTF (.glb)** or **OBJ + texture** | glTF is the modern standard, well-supported by both raylib (via cgltf) and any web engine as a fallback |
| Texture projection | Original RGB image UV-mapped onto the mesh | This is what makes the flythrough look like the actual terrain, not an abstract heightmap — weighted heavily in the "visual fidelity" criterion |

---

## 5. Module 3 — Interactive 3D Flythrough (your differentiator)

The problem statement suggests "Unity, Three.js, or Babylon.js." **Still recommend building this in your own raylib/C++ engine — but compiled to WebAssembly, not shipped as a native binary.** A plain native `.exe` would mean the flythrough and the web backend are two separate deployables, which breaks the one-monorepo/one-deployment requirement and forces some workaround to connect them. Compiling raylib to WASM via **Emscripten** keeps every advantage of using your own engine while making it a normal part of the same web deployment:

- You already have a working custom engine (RayWaves). This is real, demonstrated capability that almost no other SIH team building this PS will have — most will reach for Three.js or Unity because that's what tutorials cover. WASM doesn't dilute this: it's the same C++ rendering code, just a different compile target.
- **Same origin, no handoff.** The compiled `.wasm`/`.js`/`.html` bundle is served as a static asset by the same FastAPI process that serves the htmx pages. The viewer loads terrain data via a normal `fetch()` call to your own API — no file-path passing, no spawning a separate process, no "hacky" glue between backend and frontend.
- **Zero-install for judges.** They open a browser tab — no OS-specific binary, no missing-runtime risk on a demo laptop you don't control.
- raylib handles exactly what's needed here regardless of target: mesh loading (`Model`/`Mesh` API), free-fly camera (`Camera3D` with custom controller), texture mapping — no engine-feature gaps for this scope, and Emscripten support is first-class in raylib (documented web-build workflow, used by raylib's own official web examples).
- Judges scoring "navigability... interface intuitiveness... software stability" get a self-contained, always-reachable demo instead of one that depends on a separately distributed binary actually running on their machine.

| Component | Tool | Why |
|---|---|---|
| Renderer/engine | **raylib (C++), compiled via Emscripten** | Your existing engine codebase — reuse camera controller, mesh loading, and rendering pipeline you've already built; `emcc` produces the `.wasm`/`.js`/`.html` bundle |
| Mesh/texture loading | raylib's built-in glTF/OBJ loader, fed via `LoadModelFromMemory` | Native support; in the WASM build, mesh data arrives via `fetch()` into memory rather than from local disk |
| Camera | Custom free-fly controller (extend what you have in RayWaves) | First-person navigation is explicitly required by the PS |
| UI overlay (height readout, slope analysis) | raylib immediate-mode GUI (raygui) | Lightweight, no need for a separate UI framework — works identically in the WASM build |
| Packaging | `.wasm` + `.js` + `.html`, served as static files under e.g. `/viewer` on the FastAPI app | One artifact, one deploy — no separate binary distribution |

**Do this first, not last:** get a minimal raylib "hello triangle" compiling to WASM and served by FastAPI on day one. The Emscripten toolchain (SDK install, raylib-specific build flags) has real one-time setup friction — resolve it before integrating the actual mesh pipeline under deadline pressure.

**Stretch goal, not core:** none needed — the WASM viewer *is* the web-embedded demo, so there's no separate "web preview" to build as a fallback anymore. One less thing to scope.

---

## 6. Module 4 — Upload/Job Orchestration UI

Revised to minimize JS and cut hosting cost:

| Component | Tool | Why |
|---|---|---|
| Frontend | **htmx + server-rendered Jinja2 templates** | No SPA, no JS build step. `hx-post` handles the upload form, `hx-get` + `hx-trigger="every 2s"` polls job status and swaps in the result partial when ready. This is exactly htmx's use case — Next.js was genuine overkill for an upload→poll→result flow |
| Backend | **FastAPI** — same service as Module 1, just add routes that return HTML fragments instead of JSON for the htmx endpoints, plus a static-files mount for the compiled WASM viewer | FastAPI serves Jinja2 templates natively (`Jinja2Templates`), and `StaticFiles` serves the raylib-WASM bundle from the same process — one app, one deploy, no separate frontend host |
| 3D viewer delivery | Compiled raylib-WASM bundle mounted at `/viewer` (or similar) on the same FastAPI app | This is what makes it a true monorepo deployment — the "frontend" 3D app isn't a separate service, it's static output built by your C++ pipeline and served like any other asset |
| Job metadata | **SQLite** | Same "simplified data model" philosophy you used on AgriShield — you don't need Postgres for a hackathon demo |
| Deployment | **A $5/mo VPS (Hetzner/DigitalOcean) or Fly.io/Render free tier**, not Railway | FastAPI + Jinja2 + SQLite + the WASM static bundle is one process, one artifact — `uvicorn` behind a systemd service or a single Fly.io app is enough, and meaningfully cheaper than Railway. If judging is on-site, you may not need public hosting at all — just run it on the demo laptop |

**Why keep FastAPI instead of Go here:** the depth model (Module 1) is the module your grade actually depends on, and it only has a mature ecosystem in Python (`transformers`, `rasterio`, GDAL bindings). Splitting the orchestration layer into Go would mean running two languages for no real benefit, since FastAPI already serves htmx fragments and static WASM assets just as easily as JSON — you'd be adding a second runtime to debug at the venue for a module that isn't your bottleneck.

**Repo layout for the monorepo:**
```
depthwizard/
├── app/                # FastAPI: routes, Jinja2 templates, elevation pipeline
│   ├── main.py
│   ├── templates/
│   └── pipeline/       # depth model, calibration, mesh export
├── engine/              # raylib/C++ flythrough source
│   ├── src/
│   └── build_wasm.sh    # emcc build script → outputs into app/static/viewer/
├── app/static/viewer/    # compiled .wasm/.js/.html (build output, gitignored or committed)
└── data/                # SQLite file, sample imagery for dev
```
One `git clone`, one build step for the engine (`build_wasm.sh`), one `uvicorn app.main:app` to run everything.

---

## 7. End-to-End Data Flow

1. User uploads image via the htmx upload form → FastAPI stores it, creates job record in SQLite.
2. Pipeline detects georeferenced vs. non-georeferenced (checks for CRS metadata via rasterio).
3. Depth Anything V2 inference → relative depth map.
4. If georeferenced: sample SRTM at GCP points → least-squares scale/offset fit → absolute DSM (GeoTIFF output).
5. Heightmap → triangulated mesh → texture-mapped with original RGB → export as `.glb`, stored server-side against the job ID.
6. htmx polling swaps in the "job complete" partial: DSM download link + "Open in Flythrough" (a link to `/viewer?job=<id>`, same origin, no separate app to launch).
7. Browser loads the raylib-WASM bundle from `/viewer`; the WASM app calls `fetch("/api/jobs/<id>/mesh")` on the same FastAPI backend to pull the `.glb`, renders navigable terrain in-canvas, and overlays height/slope readout on camera position.

---

## 8. Suggested Team Split (4–6 people)

| Role | Owns | Best fit |
|---|---|---|
| ML/Elevation lead | Module 1 (depth model, calibration) | Whoever's comfortable with Python/PyTorch, even if new to geospatial specifically |
| Geospatial/data lead | GDAL/rasterio, SRTM integration, GeoTIFF I/O | Can be the same person as above if team is small |
| Mesh/graphics bridge | Module 2 (heightmap → mesh, texture UV) | Whoever's most comfortable in either Python or C++ — this is the seam role |
| Engine/rendering lead | Module 3 (raylib flythrough, Emscripten/WASM build) | **You** — direct reuse of RayWaves |
| Full-stack/integration | Module 4 (htmx templates, FastAPI glue, static-mounting the WASM bundle, deployment) | Whoever built AgriShield's frontend/backend |
| Pitch/docs | Technical documentation deliverable, demo script, slides | Rotate, but assign explicitly — the PS requires "complete source code and technical documentation" as a graded deliverable |

---

## 9. Scope Cuts if Time Runs Short (in order)

1. Drop absolute-metric calibration polish — ship a working relative-depth pipeline for non-georeferenced images first; treat georeferenced/SRTM calibration as the stretch layer once the core loop works end-to-end.
2. Reduce mesh resolution/decimate aggressively rather than fighting for real-time framerate in WebGL — WASM has a lower performance ceiling than native, so this matters more here than it would for a native build.
3. Hardcode one or two strong demo images rather than building a fully general upload pipeline — judges care that it works, not that it's infinitely flexible live.
4. If the Emscripten build genuinely won't cooperate under time pressure, the fallback is a native raylib binary run locally at the venue *for the live demo only*, while the deployed web app still shows the elevation pipeline end-to-end — not ideal against the monorepo goal, but better than no working flythrough at all. Decide this by the halfway mark, not in the last two hours.

**Never cut:** the flythrough demo itself. It's the single biggest differentiator against every other team's submission for this PS, and the PS explicitly weights "navigability of the 3D flythrough" at 50% of the total score.

---

## 10. Reference Resources

- Dataset: reference repo linked in the official PS — `github.com/IMG-PROCESS-SAC/SIH2026`
- SRTM 30m DEM: via OpenTopography API or the `elevation` Python package
- Depth Anything V2: Hugging Face model hub (`depth-anything/Depth-Anything-V2-*`)
- raylib docs: `raylib.com` — Model/Mesh/Camera3D APIs cover everything Module 3 needs
- raylib + Emscripten (Web/WASM build): raylib's official examples repo includes a documented web-build workflow (`PLATFORM_WEB` target, `emcc` flags) — start from this rather than configuring Emscripten from scratch
- FastHX (`github.com/volfpeter/fasthx`): small decorator library for FastAPI + htmx/Jinja2 partial rendering, useful for the job-status polling routes
