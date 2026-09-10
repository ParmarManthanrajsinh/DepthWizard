# AGENTS.md — DepthWizard Project Guide

Instructions and operational constraints for AI agents working in this repository.

---

## 1. Project Overview
- **Project**: DepthWizard
- **Context**: ISRO SAC · Smart India Hackathon (Problem Statement SIH26175)
- **Goal**: Transform single-view optical 2D satellite/aerial imagery into calibrated metric Digital Surface Models (DSM) and interactive real-time 3D terrain flythroughs.
- **Judging Criteria (50/50 Split)**:
  1. 50% DSM Metric Accuracy (RMSE, MAE, correlation vs reference SRTM-30m elevation).
  2. 50% 3D Visualization & Flythrough Quality (WebGL/WASM camera navigation, HUD telemetry, standalone deployability).

---

## 2. Architecture & Tech Stack

```text
Browser (HTMX + Three.js / WASM)
       │
       ▼
FastAPI Single Monorepo (app/main.py)
  ├── Routes: app/routes/ (api.py, pages.py)
  ├── Database: SQLite via SQLAlchemy (app/db/models.py)
  ├── Pipeline: app/pipeline/
  │     ├── estimator.py    (Depth Anything V2 / synthetic mock)
  │     ├── geospatial.py   (rasterio / GeoTIFF CRS & bounds)
  │     ├── calibration.py  (Least-squares affine scale/offset vs SRTM)
  │     ├── mesh_builder.py (Heightfield 2.5D triangulation to .glb)
  │     └── runner.py       (Async background task runner)
  └── Static & Templates:
        ├── app/templates/  (Jinja2 + HTMX server-rendered partials)
        ├── app/static/css/ (Hallmark modern-minimal telemetry design system)
        └── engine/         (Raylib C++ / Emscripten WASM flythrough source)
```

---

## 3. UI/UX & Design System Constraints
- **Design System**: Locked in [`design.md`](file:///e:/HackathonProjects/SIH/design.md).
- **Genre**: `modern-minimal` aerospace telemetry instrument console.
- **Typography**: Google Fonts `Inter` (sans display & body) + `JetBrains Mono` (coordinates, elevation, RMSE, IDs).
  - Display headers must stay Roman (`font-style: normal`). No italic headers.
  - No gradient text fills on headings.
- **Color Palette**:
  - `--color-paper`: `#090c10` (deep carbon void)
  - `--color-paper-2`: `#121820` (elevated deck surface)
  - `--color-rule`: `#1e293b` (hairline borders)
  - `--color-accent`: `#00e5ff` (signal cyan, strictly ≤ 5% of viewport area)
  - `--color-accent-amber`: `#f59e0b` (calibration RMSE / alert)
  - `--color-accent-green`: `#10b981` (active radar / complete)
- **Anti-Slop Disciplines**:
  - No purple/cyan radial glow blobs or blurry drop-shadows.
  - No emoji clutter in buttons or status cards (use SVG glyphs or monospace badges).
  - No re-drawn fake browser or mobile phone chrome.
  - Responsive at 320px, 375px, 414px, 768px, 1200px.

---

## 4. Operational Commands

### Run Development Server
```powershell
python run.py --port 8000
# Or using specific python version:
py -3.12 run.py --port 8000
```

### Run Test Suite
```powershell
pytest tests -v
```

### Generate Synthetic Test Data
```powershell
python scripts/generate_sample.py
```

### Build C++ / Raylib Engine to WASM
```powershell
cd engine
.\build_wasm.bat    # Windows Emscripten build
```

---

## 5. Coding & Modification Rules for Agents
1. **Preserve HTMX Contracts**: When modifying templates, do not break `hx-get`, `hx-post`, `hx-target`, or `hx-swap` bindings between `upload_form.html`, `job_status.html`, and `job_result.html`.
2. **Preserve 3D Telemetry Hooks**: `viewer.html` requires `#canvas-container`, `#hud-filename`, `#hud-crs`, `#hud-alt`, `#hud-pos`, `#hud-slope`, and `#hud-status` for `viewer.js` and `three_fallback.js`.
3. **Keep Monorepo Boundaries**: Keep processing in `app/pipeline/` independent of request parsing in `app/routes/`.
4. **Validation**: Always execute `pytest tests -v` after modifying backend, routes, or pipeline modules.
