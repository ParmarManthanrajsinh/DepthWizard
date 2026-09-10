// DepthWizard Raylib WebAssembly 3D Flythrough Controller
(function () {
  const urlParams = new URLSearchParams(window.location.search);
  const jobId = urlParams.get("job");

  const hudStatus = document.getElementById("hud-status");
  const hudFilename = document.getElementById("hud-filename");
  const hudCrs = document.getElementById("hud-crs");
  const hudAlt = document.getElementById("hud-alt");
  const hudPos = document.getElementById("hud-pos");
  const hudSlope = document.getElementById("hud-slope");
  const hudGroundSlope = document.getElementById("hud-ground-slope");
  const hudProbeDeltaH = document.getElementById("hud-probe-deltah");
  const hudShading = document.getElementById("hud-shading");

  if (!jobId) {
    if (hudStatus) hudStatus.textContent = "NO JOB ID SPECIFIED";
    return;
  }

  // Load Job metadata for HUD
  fetch(`/api/jobs/${jobId}`)
    .then((r) => r.json())
    .then((jobData) => {
      if (hudFilename) hudFilename.textContent = jobData.filename || "Terrain";
      if (hudCrs)
        hudCrs.textContent =
          jobData.crs || (jobData.is_georeferenced ? "GeoTIFF" : "Relative");
    })
    .catch((err) => {
      console.warn("Metadata fetch error:", err);
    });

  // Emscripten runtime Module configuration
  const canvas = document.getElementById("canvas");
  if (canvas) {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    window.addEventListener("resize", function () {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    });
  }

  window.Module = {
    canvas: canvas,
    print: function (text) {
      console.log("[Raylib WASM]", text);
    },
    printErr: function (text) {
      console.warn("[Raylib WASM]", text);
    },
    setStatus: function (text) {
      if (text && hudStatus && !hudStatus.textContent.includes("FPS")) {
        hudStatus.textContent = text.toUpperCase();
      }
    },
    onRuntimeInitialized: async function () {
      if (hudStatus) hudStatus.textContent = "STREAMING TERRAIN MESH...";
      try {
        const meshUrl = `/api/jobs/${jobId}/mesh`;
        const res = await fetch(meshUrl);
        if (!res.ok) throw new Error("HTTP " + res.status);
        const arrayBuf = await res.arrayBuffer();

        // Write GLB mesh to Emscripten in-memory filesystem
        window.Module.FS.writeFile("/terrain.glb", new Uint8Array(arrayBuf));

        // Ingest into Raylib engine
        const loaded = window.Module.ccall(
          "LoadTerrainFromMemory",
          "number",
          ["string"],
          ["/terrain.glb"]
        );

        if (loaded) {
          if (hudStatus) hudStatus.textContent = "RAYLIB WASM ACTIVE (60 FPS)";
          console.log("Raylib WASM: Terrain mesh mounted & loaded successfully.");
        } else {
          if (hudStatus) hudStatus.textContent = "GRID FALLBACK (PARSE ERR)";
        }
      } catch (e) {
        console.error("Failed to load mesh in WASM:", e);
        if (hudStatus) hudStatus.textContent = "MESH STREAM FAILED";
      }
    },
  };

  // Live Telemetry HUD Bridge called directly from Raylib's C++ frame loop
  window.updateWasmHUD = function (
    alt,
    posX,
    posZ,
    pitch,
    groundSlope,
    fps,
    mode,
    deltaH,
    probeStatus
  ) {
    if (hudAlt) hudAlt.textContent = `${alt} m`;
    if (hudPos) hudPos.textContent = `${posX}, ${posZ}`;
    if (hudSlope) hudSlope.textContent = `${pitch}°`;
    if (hudGroundSlope) hudGroundSlope.textContent = `${groundSlope}°`;

    if (hudProbeDeltaH) {
      if (probeStatus === 2) {
        hudProbeDeltaH.textContent = `${deltaH} m (LOCKED)`;
        hudProbeDeltaH.style.color = "#ffaa00";
      } else if (probeStatus === 1) {
        hudProbeDeltaH.textContent = "TARGET MARKED";
        hudProbeDeltaH.style.color = "#00f0ff";
      } else {
        hudProbeDeltaH.textContent = "STANDBY";
        hudProbeDeltaH.style.color = "var(--color-muted, #71717a)";
      }
    }

    if (hudShading) {
      if (mode === 0) {
        hudShading.textContent = "OPTICAL RGB";
        hudShading.style.color = "var(--color-ink)";
      } else if (mode === 1) {
        hudShading.textContent = "HILLSHADE";
        hudShading.style.color = "#ffaa00";
      } else if (mode === 2) {
        hudShading.textContent = "WIREFRAME";
        hudShading.style.color = "var(--color-accent, #ff3333)";
      }
    }

    if (
      hudStatus &&
      !hudStatus.textContent.includes("FAILED") &&
      !hudStatus.textContent.includes("ERR")
    ) {
      hudStatus.textContent = `RAYLIB WASM (${fps} FPS)`;
    }
  };

  // Focus canvas on click so Raylib receives key events (WASD, X, Space, etc.)
  if (canvas) {
    canvas.addEventListener("click", function () {
      canvas.focus();
    });
  }

  // Allow clicking shading mode badge to cycle texture / hillshade
  const shadingBtn = document.getElementById("hud-shading-btn");
  if (shadingBtn) {
    shadingBtn.addEventListener("click", function () {
      if (window.Module && window.Module.ccall) {
        window.Module.ccall("CycleRenderMode", null, [], []);
      }
    });
  }

  // Allow clicking the wireframe controls badge in HUD to toggle wireframe
  const wireframeBtn = document.getElementById("hud-wireframe-btn");
  if (wireframeBtn) {
    wireframeBtn.addEventListener("click", function () {
      if (window.Module && window.Module.ccall) {
        window.Module.ccall("ToggleWireframe", null, [], []);
      }
    });
  }

  // Allow clicking structural height probe badge to trigger raycast measurement
  const probeBtn = document.getElementById("hud-probe-btn");
  if (probeBtn) {
    probeBtn.addEventListener("click", function () {
      if (window.Module && window.Module.ccall) {
        window.Module.ccall("TriggerProbe", null, [], []);
      }
    });
  }
})();
