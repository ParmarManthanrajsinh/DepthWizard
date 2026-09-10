# AGENTS.md — DepthWizard Strict Agent Operating Rules

Operational constraints, invariant contracts, and strict disciplines for all AI coding agents working on this repository.

---

## 1. Project Invariant Goals
- **Project**: DepthWizard
- **Context**: ISRO SAC · Smart India Hackathon (Problem Statement SIH26175)
- **Judging Criteria (50/50 Split)**:
  1. 50% DSM Metric Accuracy (RMSE, MAE, correlation vs reference SRTM-30m elevation).
  2. 50% 3D Visualization & Flythrough Quality (WebGL/WASM camera navigation, HUD telemetry, standalone deployability).

---

## 2. Mandatory Rules & Invariants (DO NOT BREAK)

### Rule 1: Python Runtime & Test Verification
- **Test Command**: Run `pytest tests -v` after ANY code or template modification. All tests MUST pass before finishing.
- **Python Executable**: On this Windows machine, use the Python 3.13 installation containing GDAL/rasterio/FastAPI:
  ```powershell
  & "C:\Users\Administrator\AppData\Local\Programs\Python\Python313\python.exe" run.py --port 8000
  pytest tests -v
  ```
- **Never break existing test assertions**: Notice `test_index_page` performs a case-sensitive check for `"DepthWizard"`. Keep `"DepthWizard"` present in `base.html` title and brand markup.

### Rule 2: Preserve HTMX Contracts & Target IDs
Do NOT alter, delete, or rename these HTMX hooks between routes and templates:
- **`#upload-panel`**: Container for `upload_form.html`.
- **`#job-status-panel`**: Target container for polling and results.
- **`#job-status-card`**: Dynamic outer element that polls status.
- **`upload_form.html`**: Must maintain:
  `hx-post="/api/jobs"` · `hx-target="#job-status-panel"` · `hx-swap="innerHTML"`.
- **`job_status.html`**: Must maintain:
  `hx-get="/jobs/{{ job.id }}/status"` · `hx-trigger="load delay:1.5s"` · `hx-swap="outerHTML"`.
- **`job_result.html`**: Must maintain download links `/api/jobs/{{ job.id }}/dsm` and `/api/jobs/{{ job.id }}/mesh`, plus `/viewer?job={{ job.id }}`.

### Rule 3: Preserve 3D Viewer & Telemetry Hooks
`viewer.html` and `viewer.js` communicate with the C++ Raylib WebAssembly engine (`raylib_viewer.js` / `.wasm`) via exact DOM IDs. Never delete or rename:
- `#canvas-container` (Raylib WebGL2 canvas mount point)
- `#canvas` (Emscripten WebGL canvas)
- `#hud-filename` (Target scene name)
- `#hud-crs` (Spatial coordinate reference)
- `#hud-alt` (Real-time camera altitude in meters)
- `#hud-pos` (Camera flight X, Y coordinates)
- `#hud-slope` (Terrain pitch angle)
- `#hud-status` (Engine state: INITIALIZING, RAYLIB WASM ACTIVE, etc.)
- **Engine Stack**: Native C++ Raylib WebAssembly (`viewer.js` → `raylib_viewer.js`). Three.js is fully removed.

### Rule 4: Design System & Anti-Slop Enforcement
- **Active Theme**: Locked in [`design.md`](file:///e:/HackathonProjects/SIH/design.md) (Manifesto theme: stark carbon `#0c0c0e`, signal red `#ff3333`, chalk `#f4f4f5`, 0px sharp geometry).
- **Typography Purity**:
  - All headings must be Roman (`font-style: normal`). NO italic headings.
  - Display face: `Space Grotesk` (all-caps, bold, tracking `-0.035em`).
  - Code/Telemetry face: `JetBrains Mono`.
  - Body face: `Inter`.
- **Anti-Slop Hard Limits**:
  - No purple/cyan radial glow blobs or fuzzy box-shadows.
  - No rounded pill buttons (maintain 0px constructivist geometry).
  - No random emoji clutter on buttons (use SVG glyphs or monospace badges).
  - Accent color (`#ff3333`) strictly limited to ≤ 5% of viewport area.
  - Responsive at 320px, 375px, 414px, 768px, 1200px.

### Rule 5: Pipeline & Geospatial Resiliency
- **SRTM-30m Caching**: In `calibration.py`, `fetch_srtm_elevation_tile()` caches tiles in `data/cache/dem/`. Always maintain graceful offline fallback when OpenTopography network calls fail or when running without API keys.
- **Mesh Decimation**: In `mesh_builder.py`, maintain `decimate_terrain_grid()` for flat areas so polygon budgets stay within 60 FPS limits in WebGL and WebAssembly.
- **glTF Binary Alignment**: In `export_pure_glb()`, keep 4-byte chunk padding (`pad4`) and standard glTF 2.0 binary layout for Raylib `cgltf` and Three.js compatibility.

### Rule 6: Monorepo Cleanliness
- Keep all processing inside `app/pipeline/` independent of request parsing in `app/routes/`.
- Do NOT add unnecessary external microservices or front-end JS build steps. One FastAPI process serves everything.
- Never delete production route trees, templates, or test datasets in `data/samples/`.

---

## 3. Operational Quick Reference

```powershell
# 1. Run dev server:
& "C:\Users\Administrator\AppData\Local\Programs\Python\Python313\python.exe" run.py --port 8000

# 2. Run automated test suite:
pytest tests -v

# 3. Compile Raylib C++ Engine to WASM (EMSDK auto-discovered):
cd engine
.\build_wasm.ps1     # or .\build_wasm.bat
```
