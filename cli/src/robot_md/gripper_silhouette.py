"""Forward-kinematic gripper geometry + depth-cluster matcher.

Used by calibrate_extrinsic to observe the gripper's camera-frame
position at known joint configurations — the fiducial is the gripper
itself, so no printed marker is needed.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from robot_md.kinematics import Kinematics


def expected_points(
    frontmatter: dict[str, Any],
    joint_cfg: dict[str, float],
) -> np.ndarray:
    """Return a small set of 3D points in base frame describing the observable
    gripper geometry at this joint configuration.

    Defaults: gripper-tip point from `physics.solver.gripper.tip_offset_mm`,
    plus two jaw-corner approximations offset ±5mm perpendicular to the tool
    axis. Overrideable via optional `physics.solver.gripper.silhouette_points`.
    """
    kin = Kinematics(frontmatter)
    tip_base = np.array(kin.fk(joint_cfg), dtype=float)  # (3,)

    gripper = (frontmatter.get("physics") or {}).get("solver", {}).get("gripper", {}) or {}
    custom = gripper.get("silhouette_points")
    if custom:
        # Already in base frame per preset convention; validate shape and return.
        arr = np.asarray(custom, dtype=float)
        if arr.ndim == 2 and arr.shape[1] == 3:
            return arr

    # Default silhouette: tip + two symmetric jaw corners.
    # Since we don't have full tool-frame orientation here, approximate by
    # offsetting ±5mm in y and ±3mm in z from tip. Good enough for depth
    # matching at ~500mm standoff where pixel footprint >> 5mm.
    offsets = np.array([
        [0, 0, 0],
        [0, 5, 0],
        [0, -5, 0],
        [0, 0, 3],
    ])
    return tip_base[None, :] + offsets


def find_in_depth(
    depth_frame: np.ndarray,
    K: np.ndarray,
    expected_points_in_cam: np.ndarray,
    *,
    search_radius_mm: float = 50.0,
) -> tuple[np.ndarray | None, float]:
    """Search a window around the expected camera-frame points for a matching
    depth cluster. Returns (centroid_3d_or_None, confidence ∈ [0,1]).

    Rejects (returns (None, <0.1)) when the cluster is too sparse
    (<5 points) or too dispersed (std > 20mm).
    """
    expected = np.asarray(expected_points_in_cam, dtype=float).reshape(-1, 3)
    center = expected.mean(axis=0)  # 3-vec in camera frame (mm)

    # Project the search center to a pixel.
    fx, fy = float(K[0, 0]), float(K[1, 1])
    cx, cy = float(K[0, 2]), float(K[1, 2])
    if center[2] <= 0:
        return None, 0.0
    u0 = int(round(fx * center[0] / center[2] + cx))
    v0 = int(round(fy * center[1] / center[2] + cy))

    # Convert search radius from mm to pixels at that depth.
    radius_px = int(round((search_radius_mm / center[2]) * fx))
    radius_px = max(radius_px, 8)

    h, w = depth_frame.shape[:2]
    u_lo = max(0, u0 - radius_px)
    u_hi = min(w, u0 + radius_px)
    v_lo = max(0, v0 - radius_px)
    v_hi = min(h, v0 + radius_px)
    if u_hi <= u_lo or v_hi <= v_lo:
        return None, 0.0

    window = depth_frame[v_lo:v_hi, u_lo:u_hi]
    # Mask: non-zero depth and within ±search_radius_mm of center[2].
    lo = center[2] - search_radius_mm
    hi = center[2] + search_radius_mm
    mask = (window > 0) & (window >= lo) & (window <= hi)
    if int(mask.sum()) < 5:
        return None, 0.0

    us, vs = np.meshgrid(np.arange(u_lo, u_hi), np.arange(v_lo, v_hi))
    zs = window.astype(float)
    xs = (us - cx) * zs / fx
    ys = (vs - cy) * zs / fy

    pts = np.stack([xs[mask], ys[mask], zs[mask]], axis=1)
    if pts.shape[0] < 5:
        return None, 0.0
    std = pts.std(axis=0)
    if float(std.max()) > 20.0:
        return None, 0.05

    centroid = pts.mean(axis=0)
    n = pts.shape[0]
    confidence = min(1.0, n / 50.0) * (1.0 - min(1.0, float(std.max()) / 20.0))
    return centroid, float(confidence)
