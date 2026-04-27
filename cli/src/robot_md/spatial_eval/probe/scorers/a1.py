from __future__ import annotations

import math

from robot_md.spatial_eval.probe.scorer import register_scorer


def _l2(a, b) -> float:
    return math.sqrt(sum((float(a[i]) - float(b[i])) ** 2 for i in range(3)))


def _score_a1(answer: dict, truth: dict) -> tuple[bool, float]:
    grasps = answer.get("grasps", [])
    gold = truth.get("gold_grasps_top_k", [])
    k = int(truth.get("k", 3))
    tol = float(truth.get("tolerance_m", 0.02))
    if not grasps or not gold:
        return False, 0.0
    top_k = grasps[:k]
    for g in top_k:
        for gg in gold:
            if _l2(g["position"], gg["position"]) <= tol:
                return True, 1.0
    return False, 0.0


register_scorer("A1", _score_a1)
