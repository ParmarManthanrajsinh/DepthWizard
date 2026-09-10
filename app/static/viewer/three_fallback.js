// DepthWizard WebGL Terrain Viewer & Free-Fly Camera Controller
window.initThreeTerrainViewer = function (containerId, meshUrl) {
  const container = document.getElementById(containerId);
  if (!container) return;

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x07090e);
  scene.fog = new THREE.FogExp2(0x07090e, 0.0035);

  const camera = new THREE.PerspectiveCamera(
    60,
    window.innerWidth / window.innerHeight,
    0.1,
    2000
  );
  // Default viewpoint looking over terrain
  camera.position.set(0, 45, 85);

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.shadowMap.enabled = true;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  container.appendChild(renderer.domElement);

  // Lighting
  const hemiLight = new THREE.HemisphereLight(0xddeeff, 0x111122, 1.2);
  scene.add(hemiLight);

  const sunLight = new THREE.DirectionalLight(0xfff5e6, 2.0);
  sunLight.position.set(60, 100, 40);
  sunLight.castShadow = true;
  scene.add(sunLight);

  // Fly Controls State
  const moveState = {
    forward: false,
    backward: false,
    left: false,
    right: false,
    up: false,
    down: false,
    speed: 35.0,
  };

  let isMouseDown = false;
  let prevMouseX = 0;
  let prevMouseY = 0;
  let pitch = -0.35;
  let yaw = 0;
  let terrainMesh = null;
  let isWireframe = false;

  // Keyboard navigation
  window.addEventListener("keydown", (e) => {
    switch (e.code) {
      case "KeyW":
      case "ArrowUp":
        moveState.forward = true;
        break;
      case "KeyS":
      case "ArrowDown":
        moveState.backward = true;
        break;
      case "KeyA":
      case "ArrowLeft":
        moveState.left = true;
        break;
      case "KeyD":
      case "ArrowRight":
        moveState.right = true;
        break;
      case "Space":
        moveState.up = true;
        break;
      case "KeyC":
      case "ControlLeft":
        moveState.down = true;
        break;
      case "ShiftLeft":
        moveState.speed = 85.0; // Turbo boost
        break;
      case "KeyX":
        // Toggle wireframe
        if (terrainMesh) {
          isWireframe = !isWireframe;
          terrainMesh.traverse((child) => {
            if (child.isMesh && child.material) {
              child.material.wireframe = isWireframe;
            }
          });
        }
        break;
    }
  });

  window.addEventListener("keyup", (e) => {
    switch (e.code) {
      case "KeyW":
      case "ArrowUp":
        moveState.forward = false;
        break;
      case "KeyS":
      case "ArrowDown":
        moveState.backward = false;
        break;
      case "KeyA":
      case "ArrowLeft":
        moveState.left = false;
        break;
      case "KeyD":
      case "ArrowRight":
        moveState.right = false;
        break;
      case "Space":
        moveState.up = false;
        break;
      case "KeyC":
      case "ControlLeft":
        moveState.down = false;
        break;
      case "ShiftLeft":
        moveState.speed = 35.0;
        break;
    }
  });

  // Mouse camera rotation
  window.addEventListener("mousedown", (e) => {
    if (e.target.tagName === "CANVAS") {
      isMouseDown = true;
      prevMouseX = e.clientX;
      prevMouseY = e.clientY;
    }
  });

  window.addEventListener("mouseup", () => {
    isMouseDown = false;
  });

  window.addEventListener("mousemove", (e) => {
    if (!isMouseDown) return;
    const deltaX = e.clientX - prevMouseX;
    const deltaY = e.clientY - prevMouseY;
    prevMouseX = e.clientX;
    prevMouseY = e.clientY;

    const rotSpeed = 0.003;
    yaw -= deltaX * rotSpeed;
    pitch -= deltaY * rotSpeed;
    pitch = Math.max(-Math.PI / 2 + 0.05, Math.min(Math.PI / 2 - 0.05, pitch));
  });

  // Load GLB Mesh from FastAPI backend
  const loader = new THREE.GLTFLoader();
  const hudStatus = document.getElementById("hud-status");
  if (hudStatus) hudStatus.textContent = "Loading 3D Mesh...";

  loader.load(
    meshUrl,
    (gltf) => {
      terrainMesh = gltf.scene;
      scene.add(terrainMesh);
      if (hudStatus) hudStatus.textContent = "Flythrough Active (60 FPS)";
      console.log("Terrain GLB mesh loaded into Three.js scene successfully.");
    },
    (xhr) => {
      const pct = (xhr.loaded / xhr.total) * 100;
      if (hudStatus && isFinite(pct)) {
        hudStatus.textContent = `Streaming Mesh: ${Math.round(pct)}%`;
      }
    },
    (err) => {
      console.error("Error loading GLB mesh:", err);
      if (hudStatus) hudStatus.textContent = "Failed to load GLB mesh";
    }
  );

  // Responsive resize
  window.addEventListener("resize", () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
  });

  // Animation & HUD update loop
  let lastTime = performance.now();
  const hudAlt = document.getElementById("hud-alt");
  const hudPos = document.getElementById("hud-pos");
  const hudSlope = document.getElementById("hud-slope");

  function animate() {
    requestAnimationFrame(animate);

    const now = performance.now();
    const dt = Math.min((now - lastTime) / 1000.0, 0.1);
    lastTime = now;

    // Apply orientation
    const euler = new THREE.Euler(pitch, yaw, 0, "YXZ");
    camera.quaternion.setFromEuler(euler);

    // Compute movement in camera local coordinate frame
    const moveDir = new THREE.Vector3();
    if (moveState.forward) moveDir.z -= 1;
    if (moveState.backward) moveDir.z += 1;
    if (moveState.left) moveDir.x -= 1;
    if (moveState.right) moveDir.x += 1;
    if (moveDir.lengthSq() > 0) moveDir.normalize();

    const worldMove = moveDir.applyQuaternion(camera.quaternion);
    if (moveState.up) worldMove.y += 1;
    if (moveState.down) worldMove.y -= 1;

    camera.position.addScaledVector(worldMove, moveState.speed * dt);

    // Keep camera above minimum terrain height clamp
    if (camera.position.y < 2.0) {
      camera.position.y = 2.0;
    }

    // Update HUD values
    if (hudAlt) hudAlt.textContent = `${Math.round(camera.position.y * 10)} m`;
    if (hudPos) hudPos.textContent = `${Math.round(camera.position.x)}, ${Math.round(camera.position.z)}`;
    if (hudSlope) {
      const slopeDeg = Math.round(Math.abs(pitch) * (180 / Math.PI));
      hudSlope.textContent = `${slopeDeg}°`;
    }

    renderer.render(scene, camera);
  }

  animate();
};
