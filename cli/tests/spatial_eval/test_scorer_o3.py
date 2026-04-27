from __future__ import annotations

import pytest

from robot_md.spatial_eval.probe.scorer import score_answer

UNIT_CUBE = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0), (0, 0, 1), (1, 0, 1), (0, 1, 1), (1, 1, 1)]


def test_o3_perfect_match_iou_1():
    a = {"bbox_corners": UNIT_CUBE}
    t = {"bbox_corners": UNIT_CUBE}
    p, s = score_answer("O3", a, t)
    assert p is True and s == pytest.approx(1.0)


def test_o3_disjoint_iou_0():
    a = {"bbox_corners": UNIT_CUBE}
    t = {"bbox_corners": [(10 + x, y, z) for (x, y, z) in UNIT_CUBE]}
    p, s = score_answer("O3", a, t)
    assert p is False
    assert s == pytest.approx(0.0)


def test_o3_pass_threshold_iou_05():
    # AABBs (0..1) vs (0.5..1.5): intersection 0.5, union 1.5, iou ~ 0.33 — below 0.5
    half = [(0.5 + x, y, z) for (x, y, z) in UNIT_CUBE]
    p, _ = score_answer("O3", {"bbox_corners": UNIT_CUBE}, {"bbox_corners": half})
    assert p is False
