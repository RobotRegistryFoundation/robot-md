from __future__ import annotations

from robot_md.spatial_eval.units.base import register

code = "A1"
description = (
    "Graspable region on novel objects — identify graspable region(s) "
    "and pick orientation."
)

LIFT_MIN_CM = 5.0
HOLD_MIN_S = 2.0


def parse_answer(raw: dict) -> dict:
    grasps = raw.get("grasps")
    if not isinstance(grasps, list) or not grasps:
        raise ValueError("A1 answer requires non-empty 'grasps' list")
    parsed = []
    for g in grasps:
        if not all(k in g for k in ("position", "orientation", "score")):
            raise ValueError("each grasp requires position, orientation, score")
        parsed.append({
            "position": tuple(float(v) for v in g["position"]),
            "orientation": tuple(float(v) for v in g["orientation"]),
            "score": float(g["score"]),
        })
    parsed.sort(key=lambda g: g["score"], reverse=True)
    return {"grasps": parsed}


def execute_pass(outcome: dict) -> tuple[bool, str]:
    if outcome.get("dropped"):
        return False, "object dropped during hold"
    lifted = outcome.get("object_lifted_cm", 0.0)
    if lifted < LIFT_MIN_CM:
        return False, f"object lifted {lifted} cm < {LIFT_MIN_CM} cm"
    held = outcome.get("held_seconds", 0.0)
    if held < HOLD_MIN_S:
        return False, f"object held {held} s < {HOLD_MIN_S} s"
    return True, "ok"


class A1:
    code = code
    description = description
    parse_answer = staticmethod(parse_answer)
    execute_pass = staticmethod(execute_pass)


register(A1)
