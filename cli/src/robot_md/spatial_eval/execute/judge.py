from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class ColorParams:
    h_ranges: list[tuple[int, int]]
    s_min: int = 0
    s_max: int = 255
    v_min: int = 0
    v_max: int = 255
    min_area: int = 200


def color_centroid(bgr: np.ndarray, params: ColorParams) -> tuple[int, int, int] | None:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    mask = None
    for lo, hi in params.h_ranges:
        m = cv2.inRange(
            hsv,
            (int(lo), params.s_min, params.v_min),
            (int(hi), params.s_max, params.v_max),
        )
        mask = m if mask is None else cv2.bitwise_or(mask, m)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    big = max(contours, key=cv2.contourArea)
    area = int(cv2.contourArea(big))
    if area < params.min_area:
        return None
    M = cv2.moments(big)
    if M["m00"] == 0:
        return None
    return int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"]), area


def frame_diff_pct(a: np.ndarray, b: np.ndarray) -> float:
    """Mean absolute difference as a percentage of full-scale."""
    if a.shape != b.shape:
        raise ValueError(f"frame shapes differ: {a.shape} vs {b.shape}")
    diff = cv2.absdiff(a, b)
    return float(diff.mean()) / 255.0 * 100.0
