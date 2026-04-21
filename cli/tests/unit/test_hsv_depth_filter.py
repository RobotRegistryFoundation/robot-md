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


RED_PARAMS = {"h_ranges": [[0, 10], [170, 180]], "s_min": 100, "v_min": 80}


def test_detect_hsv_without_depth_returns_centroid():
    frame = _solid_red_frame()
    centroid = detect_hsv(frame, params=RED_PARAMS)
    assert centroid is not None
    u, v, _area = centroid
    assert 250 < u < 350
    assert 150 < v < 250


def test_detect_hsv_with_depth_bounds_excludes_wall():
    frame = _solid_red_frame()
    depth = _depth_wall_left()
    # Accept only 300-500mm (tabletop).
    centroid = detect_hsv(
        frame,
        params={**RED_PARAMS, "min_depth_mm": 300, "max_depth_mm": 500},
        depth_frame=depth,
    )
    assert centroid is not None
    u, _v, _ = centroid
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


def test_detect_hsv_roi_with_depth_bounds_excludes_wall():
    """ROI path must apply depth filter the same way — ROI mask AND color mask
    AND depth mask — so an 8m wall pixel inside the ROI window is still
    excluded when bounds declare tabletop-only depth."""
    from robot_md.detectors.hsv import detect_hsv_roi

    frame = _solid_red_frame()  # all red
    depth = _depth_wall_left()  # left half wall (8000mm), right half tabletop (400mm)

    params = {
        **RED_PARAMS,
        "roi": {"u_min": 100, "u_max": 500, "v_min": 100, "v_max": 300},
        "min_depth_mm": 300,
        "max_depth_mm": 500,
    }
    centroid = detect_hsv_roi(frame, params=params, depth_frame=depth)

    assert centroid is not None
    u, v, _ = centroid
    # ROI spans u ∈ [100, 500], but depth filter excludes u < 300 (the wall).
    # Effective region is u ∈ [300, 500]. Centroid should live there.
    assert 300 < u < 500
    assert 100 < v < 300


def test_detect_hsv_roi_accepts_depth_without_bounds_is_noop():
    """ROI detector with depth_frame but no min/max bounds returns same result as no depth."""
    from robot_md.detectors.hsv import detect_hsv_roi

    frame = _solid_red_frame()
    depth = _depth_tabletop()
    params = {**RED_PARAMS, "roi": {"u_min": 100, "u_max": 500, "v_min": 100, "v_max": 300}}

    a = detect_hsv_roi(frame, params=params)
    b = detect_hsv_roi(frame, params=params, depth_frame=depth)
    assert a == b
