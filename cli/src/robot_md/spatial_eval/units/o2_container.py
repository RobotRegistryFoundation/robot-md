from __future__ import annotations

from robot_md.spatial_eval.units.base import register

code = "O2"
description = (
    "Container reasoning — target hidden under/inside a known container; "
    "recover relationship and act."
)

LIFT_MIN_CM = 5.0


def parse_answer(raw: dict) -> dict:
    for k in ("container", "contained"):
        if k not in raw:
            raise ValueError(f"O2 answer requires '{k}'")
    return {"container": str(raw["container"]), "contained": str(raw["contained"])}


def execute_pass(outcome: dict) -> tuple[bool, str]:
    if not outcome.get("correct_container"):
        return False, "wrong container visited"
    lifted = outcome.get("target_lifted_cm", 0.0)
    if lifted < LIFT_MIN_CM:
        return False, f"target lifted {lifted} cm < {LIFT_MIN_CM} cm"
    return True, "ok"


class O2:
    code = code
    description = description
    parse_answer = staticmethod(parse_answer)
    execute_pass = staticmethod(execute_pass)


register(O2)
