from __future__ import annotations

from robot_md.spatial_eval.probe.scorer import score_answer


def test_o2_exact_match():
    a = {"container": "green_cup", "contained": "red_cube"}
    t = {"container": "green_cup", "contained": "red_cube"}
    p, s = score_answer("O2", a, t)
    assert p is True and s == 1.0


def test_o2_wrong_container():
    a = {"container": "blue_cup", "contained": "red_cube"}
    t = {"container": "green_cup", "contained": "red_cube"}
    p, s = score_answer("O2", a, t)
    assert p is False and s == 0.0
