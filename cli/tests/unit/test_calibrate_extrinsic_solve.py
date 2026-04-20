"""Kabsch-style rigid-body solve for camera→base extrinsic from (tip_cam, tip_base) pairs."""
from __future__ import annotations

import numpy as np

from robot_md.calibrate_extrinsic import CalibrationError, Sample, solve
from robot_md.extrinsic import six_vec_to_matrix


def _synthesize_samples(extrinsic_gt_6vec, n=8, noise_mm=0.0, seed=0):
    """Create ground-truth samples: tip_base random, tip_cam = (extrinsic_gt)^-1 @ tip_base."""
    rng = np.random.default_rng(seed)
    T = six_vec_to_matrix(extrinsic_gt_6vec)
    T_inv = np.linalg.inv(T)
    samples = []
    for _ in range(n):
        tip_base = rng.uniform([-200, -200, 50], [200, 200, 250])
        tip_base_h = np.append(tip_base, 1.0)
        tip_cam = (T_inv @ tip_base_h)[:3]
        if noise_mm > 0:
            tip_cam = tip_cam + rng.normal(0, noise_mm, size=3)
        samples.append(Sample(joints={}, tip_cam=tip_cam, tip_base=tip_base, confidence=1.0))
    return samples


def test_solve_recovers_extrinsic_no_noise():
    gt = [400.0, 0.0, 300.0, -2.5536, 0.0, 1.5708]
    samples = _synthesize_samples(gt, n=8, noise_mm=0.0)
    extrinsic, residual = solve(samples)
    assert residual < 0.1
    for a, b in zip(extrinsic, gt):
        assert abs(a - b) < 0.01


def test_solve_tolerates_small_noise():
    gt = [400.0, 0.0, 300.0, -2.5536, 0.0, 1.5708]
    samples = _synthesize_samples(gt, n=12, noise_mm=3.0, seed=7)
    extrinsic, residual = solve(samples)
    assert residual < 10.0
    # Translation within ~10mm.
    for i in range(3):
        assert abs(extrinsic[i] - gt[i]) < 10.0


def test_solve_rejects_collinear():
    """All samples on a line → degenerate SVD → CalibrationError."""
    samples = []
    for i in range(6):
        tip_base = np.array([i * 10.0, 0.0, 0.0])
        tip_cam = np.array([i * 10.0, 0.0, 500.0])
        samples.append(Sample(joints={}, tip_cam=tip_cam, tip_base=tip_base, confidence=1.0))
    try:
        solve(samples)
    except CalibrationError:
        return
    raise AssertionError("expected CalibrationError for collinear input")


def test_solve_rejects_too_few_samples():
    samples = [Sample(joints={}, tip_cam=np.zeros(3), tip_base=np.zeros(3), confidence=1.0)] * 2
    try:
        solve(samples)
    except CalibrationError:
        return
    raise AssertionError("expected CalibrationError for <3 samples")
