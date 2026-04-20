"""Depth-first geometric detectors — bowl, cylinder, plane.

Color-free companion to detectors/hsv.py. Primary target: white_bowl,
which HSV cannot disambiguate from walls.
"""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np


def detect_depth_shape(
    depth_frame: np.ndarray,
    K: np.ndarray,
    *,
    params: dict[str, Any],
) -> tuple[int, int, int] | None:
    """Locate a shape by depth + geometry. Returns (u, v, area) in pixels.

    params:
      shape:            "bowl" | "cylinder" | "plane"
      min_diameter_mm:  lower bound on fit diameter
      max_diameter_mm:  upper bound
      z_range_mm:       [lo, hi] depth window (camera z)
    """
    shape = params.get("shape", "bowl")
    if shape != "bowl":
        # cylinder/plane defer to future work; bowl covers the v0.7 use case.
        return None

    lo, hi = params.get("z_range_mm", [0, 65535])
    min_d = float(params["min_diameter_mm"])
    max_d = float(params["max_diameter_mm"])

    band = (depth_frame >= lo) & (depth_frame <= hi)
    mask = band.astype(np.uint8) * 255
    if mask.sum() == 0:
        return None

    # Largest connected component in the depth band.
    num, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)
    if num <= 1:
        return None
    best_idx = 1 + int(stats[1:, cv2.CC_STAT_AREA].argmax())
    area_px = int(stats[best_idx, cv2.CC_STAT_AREA])
    u_px = int(centroids[best_idx, 0])
    v_px = int(centroids[best_idx, 1])

    # Diameter estimate: project the component's bounding-box width into mm at
    # the centroid depth. fx = K[0,0].
    depth_at_center = float(depth_frame[v_px, u_px]) if depth_frame[v_px, u_px] > 0 else float(
        depth_frame[band].mean()
    )
    fx = float(K[0, 0])
    bbox_w_px = int(stats[best_idx, cv2.CC_STAT_WIDTH])
    diameter_mm = (bbox_w_px / fx) * depth_at_center
    if not (min_d <= diameter_mm <= max_d):
        return None

    return u_px, v_px, area_px


DEPTH_DETECTORS = {"depth_shape": detect_depth_shape}
