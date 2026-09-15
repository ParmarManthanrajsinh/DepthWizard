"""Regression tests for ML-integration honesty plumbing.

Covers: DepthWizard03BEstimator fallback with missing checkpoint,
runner.py model_name after simulated load failure, pages.py badge
ignoring failed latest job.
"""
import unittest
from datetime import datetime, timezone, timedelta
from PIL import Image

from app.pipeline.estimator import (
    BaseDepthEstimator,
    DepthAnythingV2Estimator,
    DepthWizard03BEstimator,
    MockDepthEstimator,
)


class TestWizardFallbackMissingCheckpoint(unittest.TestCase):
    def test_missing_checkpoint_falls_back_without_raising(self):
        est = DepthWizard03BEstimator()
        # Point at a path that cannot exist so _load() takes the missing-file path.
        est.checkpoint_path = est.checkpoint_path.parent / "definitely_not_here.pt"
        img = Image.new("RGB", (64, 64), color=(100, 150, 200))
        out = est.estimate(img)
        self.assertEqual(out.shape, (64, 64))
        # Checkpoint missing means fine-tuned weights never ran.
        self.assertTrue(est.used_fallback or est.used_pretrained_fallback)

    def test_inference_exception_sets_fallback_flag(self):
        est = DepthWizard03BEstimator()
        est._load = lambda: None
        est._initialized = True

        class _Boom:
            def __call__(self, *a, **k):
                raise RuntimeError("simulated CUDA OOM")

            def to(self, *a, **k):
                return self

            def eval(self):
                return self

        est._model = _Boom()
        img = Image.new("RGB", (32, 32), color=(10, 20, 30))
        out = est.estimate(img)
        self.assertEqual(out.shape, (32, 32))
        self.assertTrue(est.used_fallback or est.used_pretrained_fallback)

    def test_base_interface_exposes_fallback_flag(self):
        for cls in (MockDepthEstimator, DepthAnythingV2Estimator, DepthWizard03BEstimator):
            self.assertTrue(
                hasattr(cls, "used_fallback") or "used_fallback" in dir(cls("cpu") if cls is not DepthAnythingV2Estimator else cls(model_name="x")),
                f"{cls.__name__} must expose used_fallback via BaseDepthEstimator",
            )
        self.assertTrue(issubclass(MockDepthEstimator, BaseDepthEstimator))
        self.assertTrue(issubclass(DepthWizard03BEstimator, BaseDepthEstimator))


class TestRunnerModelNameAfterFailure(unittest.TestCase):
    def test_mock_estimator_labels_mock_dev_mode(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        from app.db.session import SessionLocal
        from app.db.models import Job, JobStatus
        from app.pipeline.runner import run_pipeline_for_job

        with tempfile.TemporaryDirectory() as tmp:
            img_path = Path(tmp) / "in.png"
            Image.new("RGB", (64, 64), color=(80, 120, 160)).save(img_path)
            job_id = "test-honesty-mock-label"
            db = SessionLocal()
            try:
                db.query(Job).filter(Job.id == job_id).delete()
                db.commit()
                db.add(Job(id=job_id, filename="in.png",
                           original_path=str(img_path),
                           status=JobStatus.PENDING.value))
                db.commit()
            finally:
                db.close()

            with patch("app.pipeline.runner.get_depth_estimator",
                       return_value=MockDepthEstimator()):
                run_pipeline_for_job(job_id)

            db = SessionLocal()
            try:
                job = db.query(Job).filter(Job.id == job_id).first()
                self.assertEqual(job.status, JobStatus.COMPLETED.value)
                self.assertEqual(job.model_name, "Mock Dev Mode")
            finally:
                db.query(Job).filter(Job.id == job_id).delete()
                db.commit()
                db.close()


class TestPagesBadgeIgnoresFailedJob(unittest.TestCase):
    def _session_with(self, rows):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from app.db.models import Job, Base

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        S = sessionmaker(bind=engine)
        db = S()
        for r in rows:
            db.add(Job(**r))
        db.commit()
        return db

    def test_failed_latest_job_does_not_move_badge(self):
        from app.routes.pages import get_model_context

        now = datetime.now(timezone.utc)
        db = self._session_with([
            {"id": "old-ok", "filename": "a.png", "original_path": "/tmp/a.png",
             "status": "COMPLETED", "model_name": "Mock Dev Mode",
             "created_at": now - timedelta(minutes=5)},
            {"id": "new-fail", "filename": "b.png", "original_path": "/tmp/b.png",
             "status": "FAILED", "model_name": "DepthWizard-05-R1 (fine-tuned)",
             "created_at": now},
        ])
        ctx = get_model_context(db)
        self.assertFalse(ctx["active_model_is_real"])
        self.assertEqual(ctx["active_model_name"], "MOCK ESTIMATOR [DEV MODE]")
        db.close()

    def test_completed_wizard_job_shows_finetuned_badge(self):
        from app.routes.pages import get_model_context

        now = datetime.now(timezone.utc)
        db = self._session_with([
            {"id": "old-mock", "filename": "a.png", "original_path": "/tmp/a.png",
             "status": "COMPLETED", "model_name": "Mock Dev Mode",
             "created_at": now - timedelta(minutes=5)},
            {"id": "new-wiz", "filename": "b.png", "original_path": "/tmp/b.png",
             "status": "COMPLETED", "model_name": "DepthWizard-05-R1 (fine-tuned)",
             "created_at": now},
        ])
        ctx = get_model_context(db)
        self.assertTrue(ctx["active_model_is_real"])
        self.assertEqual(ctx["active_model_name"], "DEPTHWIZARD-05-R1 [FINE-TUNED]")
        db.close()


if __name__ == "__main__":
    unittest.main()
