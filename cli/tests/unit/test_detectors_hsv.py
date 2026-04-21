"""Pure HSV detector — input ndarrays, output centroid + area."""

from __future__ import annotations

import cv2
import numpy as np

from robot_md.detectors.hsv import DETECTORS, detect_hsv, detect_hsv_roi


def _red_blob_rgb(size: tuple[int, int] = (200, 300)) -> np.ndarray:
    img = np.zeros((size[0], size[1], 3), dtype=np.uint8)
    img[:] = (240, 240, 240)  # light background (BGR)
    cv2.rectangle(img, (120, 60), (180, 120), (40, 40, 220), -1)  # red blob
    return img


def test_detect_hsv_finds_red_blob():
    img = _red_blob_rgb()
    result = detect_hsv(
        img,
        params={"h_ranges": [[0, 10], [170, 180]], "s_min": 80, "v_min": 80},
    )
    assert result is not None
    u, v, area = result
    assert 120 < u < 180
    assert 60 < v < 120
    assert area > 1000


def test_detect_hsv_returns_none_when_absent():
    img = np.full((100, 100, 3), 200, dtype=np.uint8)
    result = detect_hsv(img, params={"h_ranges": [[0, 10]], "s_min": 80, "v_min": 80})
    assert result is None


def test_detect_hsv_respects_min_area():
    img = np.zeros((200, 300, 3), dtype=np.uint8)
    img[:] = (240, 240, 240)
    # tiny red blob (5px) — below threshold
    cv2.rectangle(img, (100, 100), (105, 105), (40, 40, 220), -1)
    result = detect_hsv(
        img,
        params={"h_ranges": [[0, 10]], "s_min": 80, "v_min": 80, "min_area": 1000},
    )
    assert result is None


def test_detect_hsv_roi_restricts_search():
    img = np.zeros((200, 300, 3), dtype=np.uint8)
    img[:] = (0, 0, 0)
    # Light patch in upper-left quadrant
    cv2.rectangle(img, (20, 20), (80, 80), (230, 230, 230), -1)
    # Light patch outside ROI (bottom-right)
    cv2.rectangle(img, (220, 150), (280, 190), (230, 230, 230), -1)
    params = {"s_max": 80, "v_min": 100, "roi": {"u_max": 150, "v_max": 120}}
    result = detect_hsv_roi(img, params=params)
    assert result is not None
    u, _, _ = result
    assert u < 150


def test_DETECTORS_registry_has_both_kinds():
    assert "hsv" in DETECTORS
    assert "hsv_roi" in DETECTORS
    assert DETECTORS["hsv"] is detect_hsv
    assert DETECTORS["hsv_roi"] is detect_hsv_roi
