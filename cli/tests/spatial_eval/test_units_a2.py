from __future__ import annotations

import pytest

from robot_md.spatial_eval.units.a2_stability import execute_pass, parse_answer


def test_a2_parse_pose():
    a = parse_answer({"pose": {"x": 0.1, "y": -0.05, "yaw_rad": 1.2}})
    assert a["pose"] == {"x": 0.1, "y": -0.05, "yaw_rad": 1.2}

def test_a2_rejects_missing_yaw():
    with pytest.raises(ValueError):
        parse_answer({"pose": {"x": 0.1, "y": -0.05}})

def test_a2_execute_pass_stable():
    ok, _ = execute_pass({"post_release_diff_pct": 1.0})
    assert ok is True

def test_a2_execute_fails_unstable():
    ok, r = execute_pass({"post_release_diff_pct": 5.0})
    assert ok is False
    assert "unstable" in r.lower() or "stab" in r.lower()
