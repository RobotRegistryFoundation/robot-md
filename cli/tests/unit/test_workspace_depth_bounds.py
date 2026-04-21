"""Derive camera-frame depth bounds from declared workspace bounds + extrinsic."""

from __future__ import annotations

from robot_md.detectors.hsv import workspace_depth_bounds


def test_workspace_depth_bounds_camera_at_tripod_looking_down():
    """Camera at (400, 0, 300) looking at (200, 0, 0): workspace z corners
    project to camera-frame z (depth) roughly in [74.5, 579.4]mm. With
    margin, bounds widen a little on each side."""
    workspace_bounds = {"x": [-200, 340], "y": [-340, 340], "z": [0, 250]}
    extrinsic_6vec = [400.0, 0.0, 300.0, -2.5536, 0.0, 1.5708]
    lo, hi = workspace_depth_bounds(workspace_bounds, extrinsic_6vec)
    assert 0 <= lo <= 100  # near corners very close to camera Z axis
    assert 550 <= hi <= 650  # far corners ~580 + ~30 margin
    assert hi > lo


def test_workspace_depth_bounds_adds_safety_margin():
    """Margin widens bounds symmetrically by margin_mm on each side."""
    from robot_md.extrinsic import from_mount, matrix_to_six_vec

    workspace_bounds = {"x": [0, 100], "y": [0, 100], "z": [0, 100]}
    # Camera at (500, 0, 500) looking at workspace center (50, 50, 50).
    M = from_mount(position_mm=(500.0, 0.0, 500.0), look_at_mm=(50.0, 50.0, 50.0))
    extrinsic_6vec = matrix_to_six_vec(M)
    lo_no_margin, hi_no_margin = workspace_depth_bounds(
        workspace_bounds, extrinsic_6vec, margin_mm=0.0
    )
    lo_with_margin, hi_with_margin = workspace_depth_bounds(
        workspace_bounds, extrinsic_6vec, margin_mm=30.0
    )
    # Margin pushes each bound ~30mm outward (with `lo` clamped to 0).
    assert lo_with_margin <= lo_no_margin
    assert hi_with_margin - hi_no_margin == 30.0
    # Sanity: bounds enclose a sensible depth range around the workspace.
    assert hi_no_margin > lo_no_margin
    assert hi_no_margin < 2000  # not absurdly far
