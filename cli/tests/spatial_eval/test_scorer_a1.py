from __future__ import annotations

from robot_md.spatial_eval.probe.scorer import score_answer


def _g(p, score):
    return {"position": list(p), "orientation": [0, 0, 0, 1], "score": score}


def test_a1_top1_match():
    a = {"grasps": [_g((0.1, 0.0, 0.05), 0.9), _g((0.2, 0.0, 0.05), 0.5)]}
    t = {"gold_grasps_top_k": [_g((0.10, 0.0, 0.05), 1.0)], "k": 3, "tolerance_m": 0.02}
    p, s = score_answer("A1", a, t)
    assert p is True and s == 1.0


def test_a1_no_top_match():
    a = {"grasps": [_g((1.0, 1.0, 1.0), 0.9)]}
    t = {"gold_grasps_top_k": [_g((0.0, 0.0, 0.0), 1.0)], "k": 3, "tolerance_m": 0.02}
    p, s = score_answer("A1", a, t)
    assert p is False and s == 0.0
