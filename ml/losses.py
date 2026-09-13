import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Optional, Tuple


class ScaleShiftInvariantLoss(nn.Module):
    """
    Scale-and-Shift Invariant Loss (SSILoss).
    Aligns prediction to target using closed-form least-squares affine parameters
    s (scale) and t (shift) exclusively on valid pixels, then computes trimmed/masked L1 error.
    
    argmin_{s, t} || (s * pred + t) - target ||^2
    
    Loss = mean(| (s * pred + t) - target |) over valid mask.
    This guarantees exact scale-shift invariance matching the evaluation calibration protocol.
    """

    def __init__(self, eps: float = 1e-6):
        super().__init__()
        self.eps = eps

    def forward(
        self,
        pred: torch.Tensor,
        target: torch.Tensor,
        mask: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """
        Args:
            pred: (B, 1, H, W) or (B, H, W) predicted depth/height.
            target: (B, 1, H, W) or (B, H, W) ground truth elevation.
            mask: (B, 1, H, W) or (B, H, W) boolean valid pixel mask.
        Returns:
            Scalar tensor representing scale-shift invariant loss.
        """
        if pred.ndim == 3:
            pred = pred.unsqueeze(1)
        if target.ndim == 3:
            target = target.unsqueeze(1)
        if mask is not None and mask.ndim == 3:
            mask = mask.unsqueeze(1)

        b, _, h, w = pred.shape
        losses = []

        for i in range(b):
            p = pred[i, 0]
            t = target[i, 0]
            m = mask[i, 0] if mask is not None else torch.ones_like(p, dtype=torch.bool)
            m = m & torch.isfinite(p) & torch.isfinite(t)

            num_valid = m.sum()
            if num_valid < 4:
                # Not enough valid pixels to fit affine regression
                losses.append(torch.tensor(0.0, device=pred.device, dtype=pred.dtype))
                continue

            p_valid = p[m]
            t_valid = t[m]

            p_mean = p_valid.mean()
            t_mean = t_valid.mean()

            p_centered = p_valid - p_mean
            t_centered = t_valid - t_mean

            var_p = (p_centered ** 2).sum()
            cov_pt = (p_centered * t_centered).sum()

            scale = cov_pt / (var_p + self.eps)
            shift = t_mean - scale * p_mean

            # Aligned prediction
            p_aligned = scale * p_valid + shift
            l1 = torch.abs(p_aligned - t_valid).mean()
            losses.append(l1)

        if len(losses) == 0:
            return torch.tensor(0.0, device=pred.device, dtype=pred.dtype)

        return torch.stack(losses).mean()


class MultiScaleGradientLoss(nn.Module):
    """
    Multi-Scale Gradient Matching Loss.
    Penalizes high-frequency structural errors and edge discrepancies across
    multiple spatial resolution scales (e.g. 1x, 0.5x, 0.25x).
    """

    def __init__(self, scales: int = 3):
        super().__init__()
        self.scales = scales

    def forward(
        self,
        pred: torch.Tensor,
        target: torch.Tensor,
        mask: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        if pred.ndim == 3:
            pred = pred.unsqueeze(1)
        if target.ndim == 3:
            target = target.unsqueeze(1)
        if mask is not None and mask.ndim == 3:
            mask = mask.unsqueeze(1)

        total_loss = torch.tensor(0.0, device=pred.device, dtype=pred.dtype)
        valid_scale_count = 0

        curr_pred = pred
        curr_target = target
        curr_mask = mask.float() if mask is not None else torch.ones_like(pred)

        for s in range(self.scales):
            if s > 0:
                curr_pred = F.avg_pool2d(curr_pred, kernel_size=2, stride=2)
                curr_target = F.avg_pool2d(curr_target, kernel_size=2, stride=2)
                curr_mask = F.avg_pool2d(curr_mask, kernel_size=2, stride=2)

            if curr_pred.shape[-2] < 4 or curr_pred.shape[-1] < 4:
                break

            # Compute horizontal gradients
            diff = curr_pred - curr_target
            grad_x = torch.abs(diff[:, :, :, 1:] - diff[:, :, :, :-1])
            mask_x = (curr_mask[:, :, :, 1:] > 0.5) & (curr_mask[:, :, :, :-1] > 0.5)

            # Compute vertical gradients
            grad_y = torch.abs(diff[:, :, 1:, :] - diff[:, :, :-1, :])
            mask_y = (curr_mask[:, :, 1:, :] > 0.5) & (curr_mask[:, :, :-1, :] > 0.5)

            denom_x = mask_x.sum().clamp(min=1.0)
            denom_y = mask_y.sum().clamp(min=1.0)

            scale_loss = (grad_x * mask_x).sum() / denom_x + (grad_y * mask_y).sum() / denom_y
            total_loss = total_loss + scale_loss
            valid_scale_count += 1

        if valid_scale_count > 0:
            total_loss = total_loss / valid_scale_count

        return total_loss


class CombinedDepthLoss(nn.Module):
    """
    Combined objective for monocular depth fine-tuning:
    L = L_ssi + alpha * L_grad
    """

    def __init__(self, alpha_grad: float = 0.5):
        super().__init__()
        self.ssi_loss = ScaleShiftInvariantLoss()
        self.grad_loss = MultiScaleGradientLoss(scales=3)
        self.alpha_grad = alpha_grad

    def forward(
        self,
        pred: torch.Tensor,
        target: torch.Tensor,
        mask: Optional[torch.Tensor] = None,
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        l_ssi = self.ssi_loss(pred, target, mask)
        l_grad = self.grad_loss(pred, target, mask)
        total = l_ssi + self.alpha_grad * l_grad
        return total, l_ssi, l_grad
