import io
import unittest
from fastapi.testclient import TestClient
from PIL import Image

from app.db.session import init_db
from app.main import app
from app.pipeline.runner import run_pipeline_for_job
from scripts.generate_sample import generate_all_samples


class TestApiEndpoints(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        init_db()
        generate_all_samples()
        cls.client = TestClient(app)

    def test_health_check(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json().get("status"), "ok")

    def test_index_page(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("DepthWizard", resp.text)

    def test_list_samples(self):
        resp = self.client.get("/api/samples")
        self.assertEqual(resp.status_code, 200)
        samples = resp.json().get("samples", [])
        self.assertGreaterEqual(len(samples), 1)

    def test_upload_and_pipeline_run(self):
        # Create small test image buffer
        img = Image.new("RGB", (64, 64), color=(80, 120, 160))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        # Upload image
        resp = self.client.post(
            "/api/jobs",
            files={"file": ("test_aerial.png", buf, "image/png")}
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        job_id = data["id"]
        self.assertIsNotNone(job_id)

        # Execute pipeline for job synchronously
        run_pipeline_for_job(job_id)

        # Check job status
        job_resp = self.client.get(f"/api/jobs/{job_id}")
        self.assertEqual(job_resp.status_code, 200)
        job_data = job_resp.json()
        self.assertEqual(job_data["status"], "COMPLETED")
        self.assertEqual(job_data["progress"], 100)

        # Download generated mesh (.glb)
        mesh_resp = self.client.get(f"/api/jobs/{job_id}/mesh")
        self.assertEqual(mesh_resp.status_code, 200)
        self.assertEqual(mesh_resp.headers["content-type"], "model/gltf-binary")
        self.assertGreater(len(mesh_resp.content), 500)

        # Download DSM
        dsm_resp = self.client.get(f"/api/jobs/{job_id}/dsm")
        self.assertEqual(dsm_resp.status_code, 200)

        # Fetch preview image
        prev_resp = self.client.get(f"/api/jobs/{job_id}/preview")
        self.assertEqual(prev_resp.status_code, 200)
        self.assertEqual(prev_resp.headers["content-type"], "image/png")


if __name__ == "__main__":
    unittest.main()
