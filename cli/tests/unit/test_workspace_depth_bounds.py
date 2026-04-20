"""Derive camera-frame depth bounds from declared workspace bounds + extrinsic."""
from __future__ import annotations

import math

from robot_md.detectors.hsv import workspace_depth_bounds


def test_workspace_depth_bounds_camera_at_tripod_looking_down():
    """Camera at (400, 0, 300) looking at (200, 0, 0): workspace z in [0, 250]mm
    maps to camera z roughly in [250, 500]mm after rotation."""
    workspace_bounds = {"x": [-200, 340], "y": [-340, 340], "z": [0, 250]}
    # Extrinsic from from_mount((400,0,300), (200,0,0)) — camera +z toward workspace.
    extrinsic_6vec = [400.0, 0.0, 300.0, -2.5536, 0.0, 1.5708]
    lo, hi = workspace_depth_bounds(workspace_bounds, extrinsic_6vec)
    assert lo > 0
    assert hi > lo
    assert 200 <= lo <= 600
    assert 300 <= hi <= 800


def test_workspace_depth_bounds_adds_safety_margin():
    """Output bounds must be wider than the tightest corner-distance to
    tolerate a few cm of extrinsic error."""
    workspace_bounds = {"x": [0, 100], "y": [0, 100], "z": [0, 100]}
    extrinsic_6vec = [500.0, 0.0, 500.0, 0.0, 0.0, 0.0]  # identity rotation
    lo, hi = workspace_depth_bounds(workspace_bounds, extrinsic_6vec, margin_mm=30)
    # The closest point is the corner (100, 100, 100) vs camera (500, 0, 500):
    # distance = sqrt(400^2 + 100^2 + 400^2) ≈ 574mm; bounds should bracket.
    assert lo < 574 < hi
    # Margin of 30mm means hi-lo is at least 60mm wider than raw.
    # Raw spread of corners: ~200mm. With margin: ~260mm+.
    assert (hi - lo) >= 260
