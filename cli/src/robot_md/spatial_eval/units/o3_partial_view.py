from __future__ import annotations

from robot_md.spatial_eval.units.base import register

code = "O3"
description = (
    "Partial-view shape inference — target partly hidden; infer full extent for safe grasp."
)

LIFT_MIN_CM = 5.0
OCCLUDER_DISTURB_THRESHOLD_PCT = 5.0


def parse_answer(raw: dict) -> dict:
    corners = raw.get("bbox_corners")
    if not (isinstance(corners, list) and len(corners) == 8):
        raise ValueError("O3 answer requires 8 bbox_corners")
    return {"bbox_corners": [tuple(float(v) for v in c) for c in corners]}


def execute_pass(outcome: dict) -> tuple[bool, str]:
    lifted = outcome.get("target_lifted_cm", 0.0)
    if lifted < LIFT_MIN_CM:
        return False, f"target lifted {lifted} cm < {LIFT_MIN_CM} cm"
    disturb = outcome.get("occluder_disturbance_pct", 0.0)
    if disturb > OCCLUDER_DISTURB_THRESHOLD_PCT:
        return False, f"occluder disturbance {disturb}% > {OCCLUDER_DISTURB_THRESHOLD_PCT}%"
    return True, "ok"


class O3:
    code = code
    description = description
    parse_answer = staticmethod(parse_answer)
    execute_pass = staticmethod(execute_pass)


register(O3)
