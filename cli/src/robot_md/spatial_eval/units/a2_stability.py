from __future__ import annotations

from robot_md.spatial_eval.units.base import register

code = "A2"
description = "Stability-aware placement — choose a placement pose where the object stays put."

POST_RELEASE_DIFF_THRESHOLD_PCT = 2.0


def parse_answer(raw: dict) -> dict:
    pose = raw.get("pose") or {}
    for k in ("x", "y", "yaw_rad"):
        if k not in pose:
            raise ValueError(f"A2 pose requires '{k}'")
    return {"pose": {k: float(pose[k]) for k in ("x", "y", "yaw_rad")}}


def execute_pass(outcome: dict) -> tuple[bool, str]:
    diff = outcome.get("post_release_diff_pct", 0.0)
    if diff > POST_RELEASE_DIFF_THRESHOLD_PCT:
        return False, (
            f"unstable: post-release diff {diff:.1f}% > {POST_RELEASE_DIFF_THRESHOLD_PCT}%"
        )
    return True, "ok"


class A2:
    code = code
    description = description
    parse_answer = staticmethod(parse_answer)
    execute_pass = staticmethod(execute_pass)


register(A2)
