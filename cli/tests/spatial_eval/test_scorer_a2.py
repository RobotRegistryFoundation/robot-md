from __future__ import annotations

from robot_md.spatial_eval.probe.scorer import score_answer


def test_a2_within_stable_cluster():
    a = {"pose": {"x": 0.1, "y": 0.05, "yaw_rad": 1.2}}
    t = {
        "gold_stable_clusters": [
            {"x": 0.10, "y": 0.05, "yaw_rad": 1.2, "xy_tolerance_m": 0.02, "yaw_tolerance_rad": 0.3}
        ]
    }
    p, s = score_answer("A2", a, t)
    assert p is True and s == 1.0


def test_a2_outside_all_clusters():
    a = {"pose": {"x": 1.0, "y": 1.0, "yaw_rad": 0.0}}
    t = {
        "gold_stable_clusters": [
            {"x": 0.0, "y": 0.0, "yaw_rad": 0.0, "xy_tolerance_m": 0.02, "yaw_tolerance_rad": 0.3}
        ]
    }
    p, s = score_answer("A2", a, t)
    assert p is False and s == 0.0
