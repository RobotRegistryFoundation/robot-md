from __future__ import annotations

import pytest

from robot_md.spatial_eval.units.o1_permanence import O1, execute_pass, parse_answer


def test_o1_code_and_description():
    assert O1.code == "O1"
    assert "permanence" in O1.description.lower()


def test_o1_parse_answer_well_formed():
    raw = {"still_present": True, "position": [0.1, 0.05, 0.0]}
    a = parse_answer(raw)
    assert a == {"still_present": True, "position": (0.1, 0.05, 0.0)}


def test_o1_parse_answer_rejects_missing_position():
    with pytest.raises(ValueError, match="position"):
        parse_answer({"still_present": True})


def test_o1_execute_pass_true_when_retrieved_no_disturb():
    outcome = {"target_retrieved": True, "occluder_disturbance_pct": 1.5}
    ok, _ = execute_pass(outcome)
    assert ok is True


def test_o1_execute_pass_false_when_occluder_disturbed():
    outcome = {"target_retrieved": True, "occluder_disturbance_pct": 12.0}
    ok, reason = execute_pass(outcome)
    assert ok is False
    assert "occluder" in reason.lower()
