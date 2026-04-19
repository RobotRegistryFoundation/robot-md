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


def detect_hsv(rgb_bgr: np.ndarray, *, params: dict[str, Any]) -> tuple[int, int, int] | None:
    hsv = cv2.cvtColor(rgb_bgr, cv2.COLOR_BGR2HSV)
    mask = _hsv_mask(hsv, params)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    return _largest_centroid(mask, min_area=int(params.get("min_area", 200)))


def detect_hsv_roi(rgb_bgr: np.ndarray, *, params: dict[str, Any]) -> tuple[int, int, int] | None:
    roi = params.get("roi") or {}
    u_min = int(roi.get("u_min", 0))
    u_max = int(roi.get("u_max", rgb_bgr.shape[1]))
    v_min = int(roi.get("v_min", 0))
    v_max = int(roi.get("v_max", rgb_bgr.shape[0]))

    hsv = cv2.cvtColor(rgb_bgr, cv2.COLOR_BGR2HSV)
    mask = _hsv_mask(hsv, params)
    roi_mask = np.zeros_like(mask)
    roi_mask[v_min:v_max, u_min:u_max] = 255
    return _largest_centroid(mask & roi_mask, min_area=int(params.get("min_area", 1000)))


DETECTORS = {"hsv": detect_hsv, "hsv_roi": detect_hsv_roi}
