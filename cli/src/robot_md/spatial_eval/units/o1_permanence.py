from __future__ import annotations

from robot_md.spatial_eval.units.base import register

code = "O1"
description = "Object permanence — target visible at t=0, occluder slides over, robot answers presence + position."

OCCLUDER_DISTURB_THRESHOLD_PCT = 5.0


def parse_answer(raw: dict) -> dict:
    if "still_present" not in raw or "position" not in raw:
        raise ValueError("O1 answer requires 'still_present' and 'position'")
    pos = raw["position"]
    if not (isinstance(pos, (list, tuple)) and len(pos) == 3):
        raise ValueError("O1 position must be [x, y, z]")
    return {"still_present": bool(raw["still_present"]), "position": tuple(float(v) for v in pos)}


def execute_pass(outcome: dict) -> tuple[bool, str]:
    if not outcome.get("target_retrieved"):
        return False, "target not retrieved within timeout"
    if outcome.get("occluder_disturbance_pct", 0.0) > OCCLUDER_DISTURB_THRESHOLD_PCT:
        return False, f"occluder disturbance > {OCCLUDER_DISTURB_THRESHOLD_PCT}%"
    return True, "ok"


class O1:
    code = code
    description = description
    parse_answer = staticmethod(parse_answer)
    execute_pass = staticmethod(execute_pass)


register(O1)
