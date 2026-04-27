from __future__ import annotations

import math

from robot_md.spatial_eval.probe.scorer import register_scorer


def _score_a2(answer: dict, truth: dict) -> tuple[bool, float]:
    pose = answer.get("pose", {})
    if not pose:
        return False, 0.0
    for c in truth.get("gold_stable_clusters", []):
        dx = pose["x"] - c["x"]
        dy = pose["y"] - c["y"]
        d_xy = math.sqrt(dx * dx + dy * dy)
        d_yaw = abs(((pose["yaw_rad"] - c["yaw_rad"]) + math.pi) % (2 * math.pi) - math.pi)
        if d_xy <= c["xy_tolerance_m"] and d_yaw <= c["yaw_tolerance_rad"]:
            return True, 1.0
    return False, 0.0


register_scorer("A2", _score_a2)
