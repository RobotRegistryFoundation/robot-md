from __future__ import annotations

import cv2
import numpy as np

from robot_md.spatial_eval.execute.judge import (
    ColorParams,
    color_centroid,
    frame_diff_pct,
)

RED = ColorParams(h_ranges=[(0, 10), (170, 180)], s_min=120, v_min=80)


def _solid_red_image(h=240, w=320, blob_xy=(160, 120), radius=20) -> np.ndarray:
    img = np.zeros((h, w, 3), dtype=np.uint8)
    cv2.circle(img, blob_xy, radius, (0, 0, 255), thickness=-1)  # BGR red
    return img


def test_color_centroid_finds_red_blob():
    img = _solid_red_image()
    c = color_centroid(img, RED)
    assert c is not None
    u, v, area = c
    assert abs(u - 160) < 4
    assert abs(v - 120) < 4
    assert area > 100


def test_color_centroid_none_when_absent():
    img = np.zeros((240, 320, 3), dtype=np.uint8)
    assert color_centroid(img, RED) is None


def test_frame_diff_pct_zero_for_identical_frames():
    img = _solid_red_image()
    assert frame_diff_pct(img, img.copy()) == 0.0


def test_frame_diff_pct_high_for_disjoint_frames():
    a = _solid_red_image(blob_xy=(50, 50))
    b = _solid_red_image(blob_xy=(250, 200))
    assert frame_diff_pct(a, b) > 1.0
