from __future__ import annotations
import pytest
from robot_md.spatial_eval.units.o3_partial_view import O3, parse_answer, execute_pass

def test_o3_parse_answer_8_corners():
    raw = {"bbox_corners": [[0,0,0],[1,0,0],[0,1,0],[1,1,0],[0,0,1],[1,0,1],[0,1,1],[1,1,1]]}
    a = parse_answer(raw)
    assert len(a["bbox_corners"]) == 8

def test_o3_rejects_wrong_corner_count():
    with pytest.raises(ValueError):
        parse_answer({"bbox_corners": [[0,0,0]]})

def test_o3_execute_pass():
    ok, _ = execute_pass({"target_lifted_cm": 6.0, "occluder_disturbance_pct": 2.0})
    assert ok is True

def test_o3_execute_fails_disturbance():
    ok, r = execute_pass({"target_lifted_cm": 6.0, "occluder_disturbance_pct": 7.0})
    assert ok is False
    assert "disturb" in r.lower()
