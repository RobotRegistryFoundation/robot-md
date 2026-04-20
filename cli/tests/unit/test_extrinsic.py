"""Pure extrinsic math: 6-vec ↔ 4x4, camera_to_base, from_mount."""
from __future__ import annotations

import math

import numpy as np
import pytest

from robot_md.extrinsic import camera_to_base, from_mount, six_vec_to_matrix


def test_six_vec_to_matrix_identity_is_eye():
    M = six_vec_to_matrix((0, 0, 0, 0, 0, 0))
    assert np.allclose(M, np.eye(4))


def test_six_vec_to_matrix_pure_translation():
    M = six_vec_to_matrix((100, 200, 300, 0, 0, 0))
    assert np.allclose(M[:3, :3], np.eye(3))
    assert np.allclose(M[:3, 3], [100, 200, 300])


def test_six_vec_to_matrix_pure_z_rotation():
    M = six_vec_to_matrix((0, 0, 0, 0, 0, math.pi / 2))
    # +x should rotate to +y under 90° z-rotation
    assert np.allclose(M[:3, 0], [0, 1, 0], atol=1e-9)


def test_camera_to_base_identity_is_noop():
    result = camera_to_base((10, 20, 30), six_vec_to_matrix((0, 0, 0, 0, 0, 0)))
    assert result == pytest.approx((10, 20, 30))


def test_camera_to_base_translation_offsets():
    M = six_vec_to_matrix((100, 0, 0, 0, 0, 0))
    result = camera_to_base((10, 20, 30), M)
    assert result == pytest.approx((110, 20, 30))


def test_from_mount_builds_matrix_whose_translation_equals_position():
    M = from_mount(position_mm=(400, 0, 300), look_at_mm=(200, 0, 0))
    assert np.allclose(M[:3, 3], [400, 0, 300], atol=1e-6)


def test_from_mount_camera_sees_look_at_point_on_optical_axis():
    M = from_mount(position_mm=(400, 0, 300), look_at_mm=(200, 0, 0))
    cam_z_in_base = M[:3, 2]
    expected = np.array([200 - 400, 0, 0 - 300], dtype=float)
    expected = expected / np.linalg.norm(expected)
    assert np.allclose(cam_z_in_base, expected, atol=1e-6)


def test_camera_to_base_with_from_mount_projects_origin_to_position():
    M = from_mount(position_mm=(400, 0, 300), look_at_mm=(200, 0, 0))
    result = camera_to_base((0, 0, 0), M)
    assert result == pytest.approx((400, 0, 300), abs=1e-6)


def test_from_mount_raises_on_coincident_points():
    with pytest.raises(ValueError, match="cannot coincide"):
        from_mount(position_mm=(100, 0, 0), look_at_mm=(100, 0, 0))


def test_from_mount_raises_when_look_direction_parallel_to_up():
    # Camera at (0, 0, 100) looking straight down at origin; up=(0,0,1) is parallel.
    with pytest.raises(ValueError, match="parallel to up"):
        from_mount(position_mm=(0, 0, 100), look_at_mm=(0, 0, 0), up=(0, 0, 1))


def test_rotation_and_translation_compose_correctly():
    """Point at (10, 0, 0) in camera frame, camera at (100, 0, 0) in base
    with 90° z-rotation, should land at (100, 10, 0) in base (rotation
    applied before translation in a camera→base transform)."""
    M = six_vec_to_matrix((100, 0, 0, 0, 0, math.pi / 2))
    result = camera_to_base((10, 0, 0), M)
    assert result == pytest.approx((100, 10, 0), abs=1e-9)


def test_six_vec_to_matrix_rejects_wrong_length():
    with pytest.raises(ValueError, match="exactly 6"):
        six_vec_to_matrix((1, 2, 3, 4, 5))
