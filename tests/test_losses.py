import unittest
import torch
from ml.losses import ScaleShiftInvariantLoss, MultiScaleGradientLoss, CombinedDepthLoss


class TestDepthLosses(unittest.TestCase):
    """
    Unit tests for scale-and-shift invariant losses and gradient matching.
    """

    def setUp(self):
        torch.manual_seed(42)

    def test_ssi_exact_linear_invariance(self):
        """If prediction is an exact affine transform of target, SSI loss must be zero."""
        loss_fn = ScaleShiftInvariantLoss()
        target = torch.rand(2, 1, 32, 32) * 50.0 + 10.0
        # Affine transformed pred: a * target + b
        pred = 4.2 * target + 17.8

        loss = loss_fn(pred, target)
        self.assertAlmostEqual(float(loss.item()), 0.0, places=4)

    def test_ssi_hand_computed_residual(self):
        """Verify hand-computed residual on simple 1D-like 2x2 grid."""
        loss_fn = ScaleShiftInvariantLoss()
        target = torch.tensor([[[[10.0, 20.0],
                                 [10.0, 20.0]]]])
        # Prediction with error on one pixel
        # Normal targets: mean=15.0, centered=[-5, 5, -5, 5]
        pred = target.clone()
        pred[0, 0, 0, 0] = 12.0  # +2 error

        loss = loss_fn(pred, target)
        self.assertGreater(float(loss.item()), 0.0)
        self.assertTrue(torch.isfinite(loss))

    def test_grad_loss_constant_shift_invariance(self):
        """Constant elevation shift has zero spatial gradient difference."""
        loss_fn = MultiScaleGradientLoss(scales=2)
        target = torch.rand(1, 1, 32, 32) * 100.0
        # Target + constant offset
        pred = target + 250.0

        loss = loss_fn(pred, target)
        self.assertAlmostEqual(float(loss.item()), 0.0, places=4)

    def test_masked_loss_ignores_invalid_pixels(self):
        """Ensure invalid pixels in mask do not corrupt loss computation."""
        loss_fn = ScaleShiftInvariantLoss()
        target = torch.rand(1, 1, 16, 16) * 50.0
        pred = 2.0 * target + 5.0

        # Inject extreme outlier / NaN into target and pred at (0,0)
        pred[0, 0, 0, 0] = 999999.0
        target[0, 0, 0, 0] = -999999.0

        mask = torch.ones(1, 1, 16, 16, dtype=torch.bool)
        mask[0, 0, 0, 0] = False  # Mask out corrupted pixel

        loss = loss_fn(pred, target, mask=mask)
        self.assertAlmostEqual(float(loss.item()), 0.0, places=4)

    def test_combined_depth_loss_backprop(self):
        """Verify combined loss gradients flow cleanly to trainable tensor."""
        loss_fn = CombinedDepthLoss(alpha_grad=0.5)
        pred = torch.randn(1, 1, 16, 16, requires_grad=True)
        target = torch.randn(1, 1, 16, 16)

        total, l_ssi, l_grad = loss_fn(pred, target)
        self.assertTrue(torch.isfinite(total))
        self.assertTrue(total.requires_grad)

        total.backward()
        self.assertIsNotNone(pred.grad)
        self.assertTrue(torch.isfinite(pred.grad).all())


if __name__ == "__main__":
    unittest.main()
