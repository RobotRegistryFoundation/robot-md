from __future__ import annotations

import math

from robot_md.spatial_eval.probe.scorer import register_scorer

POSITION_TOLERANCE_M = 0.02
SCORE_DECAY_DENOM_M = 0.10  # decays linearly to 0 at 10 cm beyond tolerance


def _score_o1(answer: dict, truth: dict) -> tuple[bool, float]:
    if answer.get("still_present") != truth.get("still_present"):
        return False, 0.0
    if not answer.get("still_present"):
        return True, 1.0  # both agree absent
    a = answer["position"]
    t = truth["position"]
    d = math.sqrt(sum((float(a[i]) - float(t[i])) ** 2 for i in range(3)))
    if d <= POSITION_TOLERANCE_M:
        return True, 1.0
    return False, max(0.0, 1.0 - d / SCORE_DECAY_DENOM_M)


register_scorer("O1", _score_o1)
