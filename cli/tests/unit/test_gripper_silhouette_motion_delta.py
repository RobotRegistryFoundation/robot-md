"""Tests for find_via_motion_delta — the v0.7.3 extrinsic-free bootstrap."""

from __future__ import annotations

import numpy as np

from robot_md.gripper_silhouette import find_via_motion_delta


def _blob_depth(shape=(400, 600), center=(300, 200), radius=15, depth_mm=500, bg_mm=0):
    """Build a depth frame with a circular blob at `center`, background `bg_mm`."""
    d = np.full(shape, bg_mm, dtype=np.uint16)
    yy, xx = np.ogrid[: shape[0], : shape[1]]
    mask = np.hypot(xx - center[0], yy - center[1]) <= radius
    d[mask] = depth_mm
    return d


def _K(fx=600, cx=300, cy=200):
    return np.array([[fx, 0, cx], [0, fx, cy], [0, 0, 1]], dtype=float)


def test_moving_blob_detected():
    """Two depth frames with a blob in different positions → delta finds the new position."""
    # Prev: blob at (150, 200) depth 500mm; Curr: blob at (350, 200) depth 400mm.
    prev = _blob_depth(center=(150, 200), radius=20, depth_mm=500)
    curr = _blob_depth(center=(350, 200), radius=20, depth_mm=400)
    # Background 0 ⇒ "invalid depth" in both; only the blob regions contribute.
    # But valid mask requires depth>0 in BOTH frames. Set background to a far depth
    # so it's valid but unchanged.
    prev = np.where(prev == 0, 800, prev).astype(np.uint16)
    curr = np.where(curr == 0, 800, curr).astype(np.uint16)

    centroid, conf = find_via_motion_delta(prev, curr, _K())
    assert centroid is not None, "expected detection"
    x, y, z = centroid
    # Centroid should land in the "moved to" region near (350, 200).
    assert 300 <= (x * _K()[0, 0] / z + _K()[0, 2]) <= 400
    assert 180 <= (y * _K()[1, 1] / z + _K()[1, 2]) <= 220
    assert conf > 0.0


def test_no_motion_returns_none():
    """Identical depth frames → no motion → None."""
    prev = _blob_depth(center=(300, 200), radius=15, depth_mm=500)
    prev = np.where(prev == 0, 800, prev).astype(np.uint16)
    curr = prev.copy()
    result = find_via_motion_delta(prev, curr, _K())
    assert result[0] is None
    assert result[1] == 0.0


def test_small_motion_below_threshold_returns_none():
    """Delta of 20mm across 15px — below default threshold 60mm."""
    prev = np.full((400, 600), 500, dtype=np.uint16)
    curr = np.full((400, 600), 500, dtype=np.uint16)
    # Small patch with delta 20mm.
    yy, xx = np.ogrid[:400, :600]
    m = np.hypot(xx - 300, yy - 200) <= 15
    curr[m] = 480  # delta of only 20mm
    result = find_via_motion_delta(prev, curr, _K())
    assert result[0] is None


def test_shape_mismatch_returns_none():
    """Different-shape depth frames should return None gracefully."""
    prev = np.zeros((400, 600), dtype=np.uint16)
    curr = np.zeros((300, 400), dtype=np.uint16)
    result = find_via_motion_delta(prev, curr, _K())
    assert result[0] is None


def test_custom_threshold_accepts_smaller_motion():
    """Lowering threshold_mm catches smaller depth deltas."""
    prev = np.full((400, 600), 500, dtype=np.uint16)
    curr = np.full((400, 600), 500, dtype=np.uint16)
    yy, xx = np.ogrid[:400, :600]
    m = np.hypot(xx - 300, yy - 200) <= 20
    curr[m] = 470  # delta 30mm
    # Default threshold 60mm: None.
    r1 = find_via_motion_delta(prev, curr, _K())
    assert r1[0] is None
    # With threshold 20mm: detected.
    r2 = find_via_motion_delta(prev, curr, _K(), threshold_mm=20)
    assert r2[0] is not None


def test_prefers_larger_cluster_over_noise():
    """A big high-motion cluster (gripper) + a few noise pixels should centroid on the cluster."""
    prev = np.full((400, 600), 500, dtype=np.uint16)
    curr = np.full((400, 600), 500, dtype=np.uint16)
    yy, xx = np.ogrid[:400, :600]
    gripper = np.hypot(xx - 400, yy - 150) <= 18  # radius 18 → area ~1017 px
    curr[gripper] = 380  # delta 120mm
    # A handful of noise pixels far away.
    curr[50, 50] = 380
    curr[51, 50] = 380
    curr[52, 50] = 380

    centroid, conf = find_via_motion_delta(prev, curr, _K())
    assert centroid is not None
    # Project centroid pixel.
    K = _K()
    u = centroid[0] * K[0, 0] / centroid[2] + K[0, 2]
    v = centroid[1] * K[1, 1] / centroid[2] + K[1, 2]
    # Should be very close to (400, 150), not anywhere near (50, 50).
    assert 380 <= u <= 420
    assert 135 <= v <= 165
    assert conf > 0.5  # >500 px cluster
