"""Expected gripper geometry (from FK + preset) + depth-cluster matcher."""

from __future__ import annotations

import numpy as np

from robot_md.gripper_silhouette import expected_points, find_in_depth
from robot_md.kinematics import Kinematics


# IMPORTANT: the shared fixture YAML in cli/tests/fixtures/ does NOT have a
# physics.kinematics[] block. Construct an inline SO-ARM101-like frontmatter
# for these tests, following the pattern established in test_arm_pick_dispatch.py
# and test_kinematics_analyze_envelope.py.
def _so_arm101_fm():
    return {
        "physics": {
            "solver": {
                "convention": "DH",
                "encoder": {"steps_per_rev": 4096},
                "gripper": {
                    "tip_offset_mm": [30.0, 0.0, 0.0],
                    "open_steps": 1700,
                    "close_steps": 1200,
                },
            },
            "kinematics": [
                {
                    "id": "shoulder_pan",
                    "axis": "z",
                    "a_mm": 0.0,
                    "d_mm": 30.0,
                    "limits_deg": [-180, 180],
                },
                {
                    "id": "shoulder_lift",
                    "axis": "y",
                    "a_mm": 120.0,
                    "d_mm": 0.0,
                    "limits_deg": [-90, 90],
                },
                {
                    "id": "elbow_flex",
                    "axis": "y",
                    "a_mm": 120.0,
                    "d_mm": 0.0,
                    "limits_deg": [-90, 90],
                },
                {
                    "id": "wrist_flex",
                    "axis": "y",
                    "a_mm": 60.0,
                    "d_mm": 0.0,
                    "limits_deg": [-90, 90],
                },
                {
                    "id": "wrist_roll",
                    "axis": "x",
                    "a_mm": 0.0,
                    "d_mm": 30.0,
                    "limits_deg": [-180, 180],
                },
                {"id": "gripper", "axis": "y", "a_mm": 0.0, "d_mm": 0.0, "limits_deg": [-90, 90]},
            ],
        }
    }


def test_expected_points_shape():
    fm = _so_arm101_fm()
    kin = Kinematics(fm)
    joint_cfg = {j.id: 0.0 for j in kin.joints}
    points = expected_points(fm, joint_cfg)
    assert points.ndim == 2
    assert points.shape[1] == 3
    assert 3 <= points.shape[0] <= 16  # tip + jaw corners, small set


def test_find_in_depth_recovers_known_centroid():
    """Synthetic depth frame with a small blob at known camera XYZ — matcher
    returns that XYZ within a few mm."""
    depth = np.zeros((400, 600), dtype=np.uint16)
    # Blob at camera XYZ ≈ (0, 0, 500): pixels near (300, 200).
    cy, cx = 200, 300
    yy, xx = np.ogrid[:400, :600]
    mask = np.hypot(xx - cx, yy - cy) <= 8
    depth[mask] = 500

    K = np.array([[600, 0, 300], [0, 600, 200], [0, 0, 1]], dtype=float)
    expected_cam = np.array([[0.0, 0.0, 500.0]])  # what FK says the tip should be
    centroid, conf = find_in_depth(depth, K, expected_cam, search_radius_mm=40)
    assert centroid is not None
    assert abs(centroid[0]) < 10
    assert abs(centroid[1]) < 10
    assert abs(centroid[2] - 500) < 10
    assert conf > 0.5


def test_find_in_depth_returns_none_when_sparse():
    depth = np.zeros((400, 600), dtype=np.uint16)  # empty frame
    K = np.array([[600, 0, 300], [0, 600, 200], [0, 0, 1]], dtype=float)
    expected_cam = np.array([[0.0, 0.0, 500.0]])
    out = find_in_depth(depth, K, expected_cam, search_radius_mm=40)
    assert out[0] is None or out[1] < 0.1
