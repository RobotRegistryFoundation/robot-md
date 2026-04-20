"""HSV descriptors filter matches by depth; workspace bounds are the default."""
from __future__ import annotations

import numpy as np

from robot_md.detectors.hsv import detect_hsv


def _solid_red_frame(shape=(400, 600, 3)):
    """Solid-red BGR frame — a naive HSV detector returns the image center."""
    frame = np.zeros(shape, dtype=np.uint8)
    frame[..., 2] = 200  # BGR red channel high
    return frame


def _depth_tabletop(shape=(400, 600)):
    """400mm everywhere — simulates a single tabletop surface."""
    return np.full(shape, 400, dtype=np.uint16)


def _depth_wall_left(shape=(400, 600)):
    """Left half at 8000mm (wall), right half at 400mm (tabletop)."""
    d = np.full(shape, 8000, dtype=np.uint16)
    d[:, 300:] = 400
    return d


RED_PARAMS = {"h_min": 0, "h_max": 10, "s_min": 100, "v_min": 80}


def test_detect_hsv_without_depth_returns_centroid():
    frame = _solid_red_frame()
    centroid = detect_hsv(frame, params=RED_PARAMS)
    assert centroid is not None
    u, v, area = centroid
    assert 250 < u < 350
    assert 150 < v < 250


def test_detect_hsv_with_depth_bounds_excludes_wall():
    frame = _solid_red_frame()
    depth = _depth_wall_left()
    # Accept only 300–500mm (tabletop).
    centroid = detect_hsv(
        frame,
        params={**RED_PARAMS, "min_depth_mm": 300, "max_depth_mm": 500},
        depth_frame=depth,
    )
    assert centroid is not None
    u, v, _ = centroid
    # Centroid must be in the right half (tabletop), not the left (wall).
    assert u > 300


def test_detect_hsv_depth_all_out_of_range_returns_none():
    frame = _solid_red_frame()
    depth = np.full((400, 600), 8000, dtype=np.uint16)  # entire frame is "wall"
    centroid = detect_hsv(
        frame,
        params={**RED_PARAMS, "min_depth_mm": 300, "max_depth_mm": 500},
        depth_frame=depth,
    )
    assert centroid is None


def test_detect_hsv_accepts_depth_without_bounds_is_noop():
    """Passing depth_frame without min/max bounds must not change behavior."""
    frame = _solid_red_frame()
    depth = _depth_tabletop()
    a = detect_hsv(frame, params=RED_PARAMS)
    b = detect_hsv(frame, params=RED_PARAMS, depth_frame=depth)
    assert a == b
