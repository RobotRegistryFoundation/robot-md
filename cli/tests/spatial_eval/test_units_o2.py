from __future__ import annotations
import pytest
from robot_md.spatial_eval.units.o2_container import O2, parse_answer, execute_pass

def test_o2_parse_answer():
    a = parse_answer({"container": "green_cup", "contained": "red_cube"})
    assert a == {"container": "green_cup", "contained": "red_cube"}

def test_o2_rejects_missing_keys():
    with pytest.raises(ValueError):
        parse_answer({"container": "green_cup"})

def test_o2_execute_pass():
    ok, _ = execute_pass({"correct_container": True, "target_lifted_cm": 7.0})
    assert ok is True

def test_o2_execute_fails_wrong_container():
    ok, r = execute_pass({"correct_container": False, "target_lifted_cm": 7.0})
    assert ok is False
    assert "container" in r.lower()

def test_o2_execute_fails_no_lift():
    ok, r = execute_pass({"correct_container": True, "target_lifted_cm": 1.0})
    assert ok is False
    assert "lift" in r.lower()
