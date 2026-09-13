import io
import json
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.db.models import Job, JobStatus
from app.db.session import SessionLocal
from app.pipeline.runner import run_pipeline_for_job
from ml.config import DATA_DIR, TEST_IMAGES_DIR

client = TestClient(app)

def run_tests():
    print("=" * 65)
    print("DEPTHWIZARD — END-TO-END DEMO & INTEGRATION TESTS")
    print("=" * 65)

    # -------------------------------------------------------------
    # 1. Health and Static Endpoint Checks
    # -------------------------------------------------------------
    print("\n[CHECK 1] Server Health & Static Integrity")
    resp = client.get("/health")
    assert resp.status_code == 200, f"Health check failed: {resp.status_code}"
    print("  GET /health: OK", resp.json())

    resp = client.get("/")
    assert resp.status_code == 200
    assert "DepthWizard" in resp.text
    assert "upload-panel" in resp.text
    assert "job-status-panel" in resp.text
    print("  GET /: OK (HTML contains DepthWizard and required HTMX containers)")

    resp = client.get("/viewer")
    assert resp.status_code == 200
    assert "canvas" in resp.text
    assert "canvas-container" in resp.text
    assert "hud-status" in resp.text
    print("  GET /viewer: OK (3D Viewer page contains WebAssembly canvas and HUD)")

    # -------------------------------------------------------------
    # 2. Error Handling Suite
    # -------------------------------------------------------------
    print("\n[CHECK 2] Error Handling Verification")
    
    # 2.1 Non-existent job
    resp = client.get("/api/jobs/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
    print("  Non-existent job lookup: Returns 404 as expected")

    # 2.2 Non-existent mesh
    resp = client.get("/api/jobs/00000000-0000-0000-0000-000000000000/mesh")
    assert resp.status_code == 404
    print("  Non-existent mesh request: Returns 404 as expected")

    # 2.3 Non-existent DSM
    resp = client.get("/api/jobs/00000000-0000-0000-0000-000000000000/dsm")
    assert resp.status_code == 404
    print("  Non-existent DSM request: Returns 404 as expected")

    # -------------------------------------------------------------
    # 3. Three End-to-End Demo Tests with Potsdam Test Images
    # -------------------------------------------------------------
    potsdam_test_files = sorted(list(TEST_IMAGES_DIR.glob("*.tif")))[:3]
    if not potsdam_test_files:
        fallback = DATA_DIR / "samples" / "sample_himalayas.tif"
        if fallback.exists():
            potsdam_test_files = [fallback]

    demo_results = []

    for idx, test_file in enumerate(potsdam_test_files, start=1):
        print(f"\n" + "-" * 65)
        print(f"RUNNING TEST {idx}: {test_file.name}")
        print("-" * 65)

        assert test_file.exists(), f"Test file {test_file} not found"

        # Simulate UI Upload via HTMX Form (HX-Request header)
        with open(test_file, "rb") as f:
            file_bytes = f.read()

        resp = client.post(
            "/api/jobs",
            files={"file": (test_file.name, file_bytes, "image/tiff")},
            headers={"HX-Request": "true"},
        )

        assert resp.status_code == 200, f"Upload failed: {resp.status_code} {resp.text}"
        assert "job-status-card" in resp.text, "Response missing HTMX job-status-card"
        
        # Extract Job ID from database
        db = SessionLocal()
        latest_job = db.query(Job).order_by(Job.created_at.desc()).first()
        job_id = latest_job.id
        db.close()
        print(f"  Job created successfully. ID: {job_id}")

        # Run pipeline synchronously for the test
        t0 = time.time()
        run_pipeline_for_job(job_id)
        elapsed = time.time() - t0

        # Verify Job Status
        db = SessionLocal()
        job = db.query(Job).filter(Job.id == job_id).first()
        db.close()

        assert job.status == JobStatus.COMPLETED.value, f"Job failed with status {job.status}: {job.error_message}"
        print(f"  Inference & pipeline completed in {elapsed:.2f}s")
        print(f"  Model: {job.model_name}")
        print(f"  Elevation Range: [{job.elevation_min:.1f}m, {job.elevation_max:.1f}m] (Delta-h: {job.elevation_max - job.elevation_min:.1f}m)")
        print(f"  Terrain Slope: Mean {job.mean_slope_deg:.1f} deg, Max {job.max_slope_deg:.1f} deg")

        # Verify HTMX polling status endpoint
        resp_status = client.get(f"/jobs/{job_id}/status")
        assert resp_status.status_code == 200
        assert "COMPLETED" in resp_status.text or "COMPLETE" in resp_status.text or "FLYTHROUGH" in resp_status.text.upper()
        print(f"  GET /jobs/{job_id}/status: HTMX Partial returned completion card")

        # Verify DSM GeoTIFF Download
        resp_dsm = client.get(f"/api/jobs/{job_id}/dsm")
        assert resp_dsm.status_code == 200
        assert len(resp_dsm.content) > 1000
        print(f"  GET /api/jobs/{job_id}/dsm: Received GeoTIFF ({len(resp_dsm.content) / 1024:.1f} KB)")

        # Verify Binary glTF 3D Mesh
        resp_mesh = client.get(f"/api/jobs/{job_id}/mesh")
        assert resp_mesh.status_code == 200
        assert resp_mesh.content[:4] == b"glTF", "Mesh is not a valid glTF 2.0 binary"
        print(f"  GET /api/jobs/{job_id}/mesh: Received valid binary glTF ({len(resp_mesh.content) / 1024:.1f} KB)")

        # Verify 2D Relief Preview
        resp_prev = client.get(f"/api/jobs/{job_id}/preview")
        assert resp_prev.status_code == 200
        assert len(resp_prev.content) > 1000
        print(f"  GET /api/jobs/{job_id}/preview: Received colorized relief preview PNG ({len(resp_prev.content) / 1024:.1f} KB)")

        # Verify 3D Flythrough Viewer integration
        resp_view = client.get(f"/viewer?job={job_id}")
        assert resp_view.status_code == 200
        assert job_id in resp_view.text
        print(f"  GET /viewer?job={job_id}: Viewer initialized for scene")

        demo_results.append({
            "test_num": idx,
            "input_rgb": test_file.name,
            "model": job.model_name,
            "inference": f"Completed ({elapsed:.2f}s)",
            "backend": "FastAPI (Job state COMPLETED, 200 OK)",
            "frontend": "HTMX partial swapped + Raylib WASM viewer linked",
            "output": f"DSM ({len(resp_dsm.content)/1024:.1f}KB), GLB ({len(resp_mesh.content)/1024:.1f}KB), Preview ({len(resp_prev.content)/1024:.1f}KB)",
            "result": "PASS",
        })

    print("\n" + "=" * 65)
    print("END-TO-END DEMO TEST SUMMARY")
    print("=" * 65)
    for r in demo_results:
        print(f"TEST {r['test_num']}")
        print(f"  Input RGB:  {r['input_rgb']}")
        print(f"  Model:      {r['model']}")
        print(f"  Inference:  {r['inference']}")
        print(f"  Backend:    {r['backend']}")
        print(f"  Frontend:   {r['frontend']}")
        print(f"  Output:     {r['output']}")
        print(f"  Result:     {r['result']}")
        print(f"  Status:     PASS\n")
    print("=" * 65)
    return True

if __name__ == "__main__":
    run_tests()
