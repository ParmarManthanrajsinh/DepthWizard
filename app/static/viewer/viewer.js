// DepthWizard 3D Flythrough Controller (Dual: Raylib WASM / WebGL Fallback)
(async function () {
  const urlParams = new URLSearchParams(window.location.search);
  const jobId = urlParams.get("job");

  if (!jobId) {
    document.getElementById("hud-status").textContent = "No Job ID provided";
    return;
  }

  const meshUrl = `/api/jobs/${jobId}/mesh`;
  const infoUrl = `/api/jobs/${jobId}`;

  try {
    const res = await fetch(infoUrl);
    const jobData = await res.json();
    document.getElementById("hud-filename").textContent = jobData.filename || "Terrain";
    document.getElementById("hud-crs").textContent = jobData.crs || (jobData.is_georeferenced ? "GeoTIFF" : "Relative");
  } catch (e) {
    console.warn("Could not fetch job metadata:", e);
  }

  // Check if Raylib WASM module is present; if not, initialize Three.js viewer
  const wasmScript = document.querySelector('script[src*="raylib_viewer.js"]');
  if (wasmScript && window.Module && window.Module._main) {
    console.log("Raylib WASM runtime detected. Initializing Raylib Canvas...");
  } else {
    console.log("Launching WebGL 3D Flythrough Viewer...");
    if (window.initThreeTerrainViewer) {
      window.initThreeTerrainViewer("canvas-container", meshUrl);
    }
  }
})();
