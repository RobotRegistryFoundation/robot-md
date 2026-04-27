from __future__ import annotations
import pytest
from robot_md.spatial_eval.units.a1_grasp import A1, parse_answer, execute_pass

def test_a1_parse_ranked_grasps():
    raw = {"grasps": [
        {"position": [0.1, 0.0, 0.05], "orientation": [0,0,0,1], "score": 0.9},
        {"position": [0.0, 0.1, 0.05], "orientation": [0,0,0,1], "score": 0.5},
    ]}
    a = parse_answer(raw)
    assert len(a["grasps"]) == 2
    assert a["grasps"][0]["score"] >= a["grasps"][1]["score"]

def test_a1_rejects_empty_grasp_list():
    with pytest.raises(ValueError):
        parse_answer({"grasps": []})

def test_a1_execute_pass_lift_and_hold():
    ok, _ = execute_pass({"object_lifted_cm": 6.0, "held_seconds": 2.5, "dropped": False})
    assert ok is True

def test_a1_execute_fails_drop():
    ok, r = execute_pass({"object_lifted_cm": 6.0, "held_seconds": 2.5, "dropped": True})
    assert ok is False
    assert "drop" in r.lower()
