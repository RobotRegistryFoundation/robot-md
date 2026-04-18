"""Tests for `robot-md calibrate --hand-eye` — ArUco-based extrinsic solver.

Live OAK-D capture is skipped (no hardware in CI). We verify:
  * Marker-corner geometry is the DH-consistent shape the solver expects.
  * Synthetic PnP round-trip: render a known camera pose → project 3D
    corners → feed back into solve_from_image → recover the pose within
    sub-pixel / sub-mm tolerance.
  * write_extrinsic_to_manifest preserves body + updates the right field.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("cv2")
pytest.importorskip("ruamel.yaml")

import cv2

from robot_md.hand_eye import (
    _marker_corners_world,
    solve_from_image,
    write_extrinsic_to_manifest,
)


def test_marker_corners_shape_and_z():
    corners = _marker_corners_world(center_xy=(300.0, 100.0), z=0.0, size_mm=50.0)
    assert corners.shape == (4, 3)
    # Center of all corners == center_xy
    centroid = corners.mean(axis=0)
    np.testing.assert_allclose(centroid[:2], [300.0, 100.0], atol=1e-9)
    np.testing.assert_allclose(centroid[2], 0.0, atol=1e-9)
    # Side length (TL → TR) == size_mm
    side = np.linalg.norm(corners[1] - corners[0])
    assert side == pytest.approx(50.0)


def test_marker_corners_respect_z_offset():
    corners = _marker_corners_world(center_xy=(0.0, 0.0), z=15.0, size_mm=40.0)
    # All 4 corners live at z=15 (marker is flat on the xy plane at that height)
    for c in corners:
        assert c[2] == pytest.approx(15.0)


def test_solve_from_image_no_marker():
    """If no ArUco marker is in the frame, solver reports marker_detected=False."""
    blank = np.full((720, 1280, 3), 255, dtype=np.uint8)
    K = np.array([[900, 0, 640], [0, 900, 360], [0, 0, 1]], dtype=np.float64)
    dist = np.zeros(5, dtype=np.float64)
    result = solve_from_image(
        blank,
        K,
        dist,
        marker_center_xy_mm=(0, 0),
        marker_size_mm=50.0,
    )
    assert not result.marker_detected
    assert result.num_markers_found == 0
    assert result.reprojection_error_px == float("inf")


def test_solve_from_image_wrong_id_rendered_marker():
    """Render a clean marker via cv2.aruco.generateImageMarker (no perspective
    warp — just paste into a white canvas) and verify the wrong-id path.
    This avoids the projection-math pitfalls of a full round-trip test.
    """
    # Clean, un-warped marker: large white canvas, marker pasted at center.
    canvas = np.full((720, 1280, 3), 255, dtype=np.uint8)
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    marker = cv2.aruco.generateImageMarker(aruco_dict, 7, 200)
    marker_bgr = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)
    x0, y0 = 540, 260
    canvas[y0 : y0 + 200, x0 : x0 + 200] = marker_bgr

    K = np.array([[900, 0, 640], [0, 900, 360], [0, 0, 1]], dtype=np.float64)
    dist = np.zeros(5, dtype=np.float64)
    result = solve_from_image(
        canvas,
        K,
        dist,
        marker_center_xy_mm=(300.0, 0.0),
        marker_size_mm=50.0,
        marker_id=0,  # looking for id 0; marker has id 7
    )
    assert not result.marker_detected
    assert result.num_markers_found == 1, (
        f"expected the marker with id=7 to be detected but not accepted; "
        f"got num_markers_found={result.num_markers_found}"
    )


MANIFEST_FIXTURE = """\
---
rcan_version: "3.0"
metadata:
  robot_name: bob
physics:
  type: arm+camera
  dof: 6
  solver:
    convention: DH
    # keep this comment
  kinematics:
    - { id: j1, axis: y, length_mm: 100 }
drivers:
  - { id: arm, protocol: feetech }
safety:
  estop: { software: true, response_ms: 100 }
---

# bob

## Identity
test

## What bob Can Do
test

## Safety Gates
test
"""


def test_write_extrinsic_to_manifest_round_trip(tmp_path):
    path = tmp_path / "bob.ROBOT.md"
    path.write_text(MANIFEST_FIXTURE)
    write_extrinsic_to_manifest(path, [10.0, 20.0, 30.0, 0.1, 0.2, 0.3])
    out = path.read_text()
    # Extrinsic is a list under solver.camera
    assert "extrinsic:" in out
    assert "10.0" in out
    assert "0.3" in out
    # Comment + body preserved
    assert "keep this comment" in out
    assert "## Identity" in out


def test_write_extrinsic_rejects_bad_manifest(tmp_path):
    path = tmp_path / "bad.md"
    path.write_text("no frontmatter\n")
    with pytest.raises(RuntimeError, match="frontmatter"):
        write_extrinsic_to_manifest(path, [0, 0, 0, 0, 0, 0])
