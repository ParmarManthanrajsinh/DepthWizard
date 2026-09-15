# EX04A_AUDIT.md

## Current Pipeline Audit

### 1. Depth Prediction
- **File:** `app/pipeline/estimator.py`
- **Class:** `DepthWizard03BEstimator` (and `DepthAnythingV2Estimator`, `MockDepthEstimator`)
- **Function:** `estimate(self, image: Image.Image) -> np.ndarray`
- **Data Flow:** RGB Image `->` Normalized Float Tensor `->` LoRA / Depth Anything Model `->` Float32 Numpy Array.
- **Output:** The model outputs metric AGL (Above Ground Level) relative depth. Large values typically mean closer to the sensor (taller).

### 2. Depth Normalization & Depth-to-Height Conversion
- **File:** `app/pipeline/calibration.py`
- **Function:** `calibrate_elevation`
- **Data Flow:** Takes raw depth output. If georeferenced, it fetches SRTM-30m baseline and adds the predicted AGL directly to the ground DEM (`calibrated = (d_norm + ref).astype(np.float32)`).
- **Output Range:** The uncalibrated values are metric AGL. After calibration, they are absolute elevations (ASL) in meters.

### 3. Height-map Postprocessing
- Currently, there is NO explicit postprocessing / smoothing of the height map before mesh generation. Extreme values (spikes) from the model prediction pass directly to the mesher.

### 4. Mesh Vertex & Index Generation
- **File:** `app/pipeline/mesh_builder.py`
- **Function:** `generate_terrain_mesh` and `decimate_terrain_grid`
- **Mesh Resolution:** Fixed `target_res = MESH_GRID_RESOLUTION` (typically config-driven).
- **Z Scaling:** `grid_y = h_grid * height_scale`. `height_scale` defaults to 1.0 for 1:1 metric height.

### 5. Texture Coordinates & Rendering
- **File:** `app/pipeline/mesh_builder.py` (Export) and Viewer logic.
- **UVs:** `grid_u, grid_v = np.meshgrid(us, vs)` linearly mapped to `[0.0, 1.0]`. Texture is embedded into the `.glb` and mapped across the mesh.

### Diagnostic Conclusion
Extreme values enter the pipeline directly from the depth model (`DepthWizard03BEstimator`). Since it predicts AGL, trees and buildings (or model artifacts) can have large, abrupt height jumps (e.g., 30m vertical walls for a building). These are added directly to the SRTM terrain and meshed. The absence of slope limiting and smoothing causes sharp spikes and pyramid mountains.
