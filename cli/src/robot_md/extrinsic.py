"""Extrinsic math: 6-vec ↔ 4x4, point transformation, mount builder.

Manifest stores extrinsic as a 6-vector `[tx, ty, tz, rx, ry, rz]` in mm/radians.
Rotations are **extrinsic XYZ Euler** (world-fixed axes: rotate `rx` about world
x, then `ry` about world y, then `rz` about world z), equivalent to
`R = Rz @ Ry @ Rx` applied to column vectors. The same convention is used for
both serialization and deserialization, so round-trips are exact.

Convention: the 4x4 `M` is camera→base. Given a point `p_cam` in camera frame,
`p_base = M @ [p_cam, 1]`.
"""

from __future__ import annotations

import math

import numpy as np


def six_vec_to_matrix(vec):
    """[tx, ty, tz, rx, ry, rz] → 4x4 camera→base homogeneous matrix.

    Rotations are extrinsic XYZ Euler (world-fixed axes: rotate rx about world
    x, then ry about world y, then rz about world z). Applied to column vectors
    this composes as `R = Rz @ Ry @ Rx`.
    """
    if len(vec) != 6:
        raise ValueError(f"six-vec must have exactly 6 elements, got {len(vec)}")
    tx, ty, tz, rx, ry, rz = [float(v) for v in vec]
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    R = Rz @ Ry @ Rx
    M = np.eye(4)
    M[:3, :3] = R
    M[:3, 3] = [tx, ty, tz]
    return M


def matrix_to_six_vec(M):
    """4x4 → [tx, ty, tz, rx, ry, rz]. Inverse of six_vec_to_matrix (XYZ Euler)."""
    M = np.asarray(M, dtype=float)
    t = M[:3, 3]
    R = M[:3, :3]
    sy = -R[2, 0]
    cy = math.sqrt(R[0, 0] ** 2 + R[1, 0] ** 2)
    if cy < 1e-9:
        rx = 0.0
        ry = math.atan2(sy, cy)
        rz = math.atan2(-R[0, 1], R[1, 1])
    else:
        rx = math.atan2(R[2, 1], R[2, 2])
        ry = math.atan2(sy, cy)
        rz = math.atan2(R[1, 0], R[0, 0])
    return (float(t[0]), float(t[1]), float(t[2]), rx, ry, rz)


def camera_to_base(point_cam_mm, extrinsic):
    """Apply the camera→base extrinsic to a camera-frame point.

    `extrinsic` may be a 6-vector (converted via six_vec_to_matrix) or a 4x4
    array-like. Returns (x, y, z) in base frame, in mm.
    """
    M = np.asarray(extrinsic, dtype=float)
    if M.ndim == 1 and M.size == 6:
        M = six_vec_to_matrix(tuple(M))
    elif M.shape != (4, 4):
        raise ValueError(f"extrinsic must be 4x4 or 6-vec, got shape {M.shape}")
    p = np.array([point_cam_mm[0], point_cam_mm[1], point_cam_mm[2], 1.0])
    q = M @ p
    return (float(q[0]), float(q[1]), float(q[2]))


def from_mount(*, position_mm, look_at_mm, up=(0, 0, 1)):
    """Build a camera→base 4x4 from a human-readable mount description.

    The camera sits at `position_mm` in base frame, with its +z optical axis
    pointing toward `look_at_mm`, and `up` aligned with the world up.
    `up` defaults to base-frame +z; callers whose robot uses a different up
    axis must pass it explicitly.

    Camera convention: +z = forward (optical axis), +x = right, +y = down
    (OpenCV-compatible).
    """
    pos = np.array(position_mm, dtype=float)
    target = np.array(look_at_mm, dtype=float)
    up_v = np.array(up, dtype=float)
    forward = target - pos
    n = np.linalg.norm(forward)
    if n < 1e-9:
        raise ValueError("position_mm and look_at_mm cannot coincide")
    forward = forward / n
    right = np.cross(forward, up_v)
    rn = np.linalg.norm(right)
    if rn < 1e-9:
        raise ValueError("look direction parallel to up; pick a different up vector")
    right = right / rn
    down = np.cross(forward, right)
    R = np.column_stack([right, down, forward])
    M = np.eye(4)
    M[:3, :3] = R
    M[:3, 3] = pos
    return M
