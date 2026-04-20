"""HSV-based centroid detectors.

Inputs: BGR image (numpy ndarray HxWx3, uint8), params dict from the manifest's
`vision.object_descriptors[].params`.

Returns: (u, v, area_px2) or None. No hardware, no I/O.
"""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np


def _largest_centroid(mask: np.ndarray, min_area: int = 200) -> tuple[int, int, int] | None:
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    big = max(contours, key=cv2.contourArea)
    area = int(cv2.contourArea(big))
    if area < min_area:
        return None
    M = cv2.moments(big)
    if M["m00"] == 0:
        return None
    return int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"]), area


def _hsv_mask(hsv: np.ndarray, params: dict[str, Any]) -> np.ndarray:
    s_min = int(params.get("s_min", 0))
    s_max = int(params.get("s_max", 255))
    v_min = int(params.get("v_min", 0))
    v_max = int(params.get("v_max", 255))
    h_ranges = params.get("h_ranges")
    if h_ranges:
        combined = None
        for lo, hi in h_ranges:
            m = cv2.inRange(hsv, (int(lo), s_min, v_min), (int(hi), s_max, v_max))
            combined = m if combined is None else (combined | m)
        return combined
    return cv2.inRange(hsv, (0, s_min, v_min), (180, s_max, v_max))


def _depth_mask(depth_frame: np.ndarray, params: dict[str, Any]) -> np.ndarray | None:
    """Return a uint8 mask where depth is within [min_depth_mm, max_depth_mm]
    OR unknown (value 0). Stereo depth has holes on textureless surfaces
    (painted LEGO, matte table); we accept unknown-depth pixels so the
    color match can survive and let the caller resolve the real depth
    from surrounding valid pixels at resolve-time.

    Returns None when no bounds are declared in params (depth ignored).
    """
    min_d = params.get("min_depth_mm")
    max_d = params.get("max_depth_mm")
    if min_d is None and max_d is None:
        return None
    lo = int(min_d) if min_d is not None else 0
    hi = int(max_d) if max_d is not None else 65535
    unknown = depth_frame == 0
    in_range = (depth_frame >= lo) & (depth_frame <= hi)
    return (unknown | in_range).astype(np.uint8) * 255


def detect_hsv(
    rgb_bgr: np.ndarray,
    *,
    params: dict[str, Any],
    depth_frame: np.ndarray | None = None,
) -> tuple[int, int, int] | None:
    """Color-mask detector with optional depth filtering.

    When ``depth_frame`` is provided AND ``params`` declares
    ``min_depth_mm`` / ``max_depth_mm``, the output mask is the joint
    (color AND depth). Otherwise depth is ignored (backward compatible).
    """
    hsv = cv2.cvtColor(rgb_bgr, cv2.COLOR_BGR2HSV)
    mask = _hsv_mask(hsv, params)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))

    if depth_frame is not None:
        dmask = _depth_mask(depth_frame, params)
        if dmask is not None:
            mask = cv2.bitwise_and(mask, dmask)

    return _largest_centroid(mask, min_area=int(params.get("min_area", 200)))


def detect_hsv_roi(
    rgb_bgr: np.ndarray,
    *,
    params: dict[str, Any],
    depth_frame: np.ndarray | None = None,
) -> tuple[int, int, int] | None:
    roi = params.get("roi") or {}
    u_min = int(roi.get("u_min", 0))
    u_max = int(roi.get("u_max", rgb_bgr.shape[1]))
    v_min = int(roi.get("v_min", 0))
    v_max = int(roi.get("v_max", rgb_bgr.shape[0]))

    hsv = cv2.cvtColor(rgb_bgr, cv2.COLOR_BGR2HSV)
    mask = _hsv_mask(hsv, params)
    roi_mask = np.zeros_like(mask)
    roi_mask[v_min:v_max, u_min:u_max] = 255
    mask = mask & roi_mask

    if depth_frame is not None:
        dmask = _depth_mask(depth_frame, params)
        if dmask is not None:
            mask = cv2.bitwise_and(mask, dmask)

    return _largest_centroid(mask, min_area=int(params.get("min_area", 1000)))


DETECTORS = {"hsv": detect_hsv, "hsv_roi": detect_hsv_roi}


def workspace_depth_bounds(
    workspace_bounds: dict[str, list[float]],
    extrinsic_6vec: list[float],
    *,
    margin_mm: float = 30.0,
) -> tuple[float, float]:
    """Project the 8 corners of the workspace cuboid into camera frame and
    return (min_depth, max_depth) suitable for an HSV detector's depth
    filter.

    workspace_bounds: {'x': [lo, hi], 'y': [lo, hi], 'z': [lo, hi]} in base frame (mm).
    extrinsic_6vec:   [tx, ty, tz, rx, ry, rz] — camera pose in base frame.
    margin_mm:        symmetric slop added to both bounds.

    Returns (min_depth, max_depth) in millimeters, both >= 0.

    Z-depth (camera-frame Z), matching what OAK-D/similar depth cameras store per-pixel.
    """
    import numpy as np
    from robot_md.extrinsic import six_vec_to_matrix

    T_cam_in_base = six_vec_to_matrix(extrinsic_6vec)
    T_base_in_cam = np.linalg.inv(T_cam_in_base)

    xs = workspace_bounds["x"]
    ys = workspace_bounds["y"]
    zs = workspace_bounds["z"]
    corners = np.array(
        [[x, y, z, 1.0] for x in xs for y in ys for z in zs],
        dtype=float,
    )  # shape (8, 4)

    corners_cam = (T_base_in_cam @ corners.T).T[:, :3]  # (8, 3)
    depths = corners_cam[:, 2]  # Z-depth — matches what the depth camera image stores.
    lo = max(0.0, float(depths.min()) - margin_mm)
    hi = max(lo + 1.0, float(depths.max()) + margin_mm)
    return lo, hi
