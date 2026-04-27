from __future__ import annotations

import pytest

from robot_md.spatial_eval.probe.scorer import score_answer


def test_dispatch_to_unit_scorer_o1():
    answer = {"still_present": True, "position": (0.1, 0.05, 0.0)}
    truth = {"still_present": True, "position": (0.10, 0.05, 0.01)}
    passed, score = score_answer("O1", answer, truth)
    assert passed is True
    assert score == pytest.approx(1.0)


def test_dispatch_unknown_unit_raises():
    with pytest.raises(KeyError):
        score_answer("Z9", {}, {})
