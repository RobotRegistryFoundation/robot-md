"""LeRobot arm.* / gripper.* handlers.

Wraps the connected robot's send_action interface with simple per-capability
action plans. Plans are intentionally generic — a real adapter would compute IK
or invoke a learned policy. For SP3, the goal is to prove dispatch plumbing;
trajectory quality is out of scope.
"""

from __future__ import annotations

from robot_md.backends.base import ExecutionEvent, ExecutionResult


def _validate_pick_args(args: dict) -> ExecutionResult | None:
    if "target" not in args:
        return ExecutionResult(
            status="error",
            trajectory=None,
            events=[],
            error={"reason": "missing_args", "detail": "arm.pick requires 'target'"},
        )
    if not isinstance(args["target"], str):
        return ExecutionResult(
            status="error",
            trajectory=None,
            events=[],
            error={"reason": "schema_violation", "detail": "'target' must be string"},
        )
    return None


def arm_pick(backend, args: dict, *, dry_run: bool, estop) -> ExecutionResult:
    bad = _validate_pick_args(args)
    if bad is not None:
        return bad
    target = args["target"]
    approach_height_mm = float(args.get("approach_height_mm", 50))
    plan = [
        {
            "phase": "approach",
            "joints": [0.0, -0.3, 0.6, 0.0, 0.0, 0.0],
            "approach_height_mm": approach_height_mm,
            "target": target,
        },
        {"phase": "descend", "joints": [0.0, -0.5, 0.4, 0.0, 0.0, 0.0]},
        {"phase": "grasp", "joints": [0.0, -0.5, 0.4, 0.0, 0.0, 0.6]},
        {"phase": "lift", "joints": [0.0, -0.3, 0.6, 0.0, 0.0, 0.6]},
    ]
    if dry_run:
        return ExecutionResult(
            status="ok",
            trajectory=plan,
            events=[
                ExecutionEvent(kind="dry_run", data={"capability": "arm.pick", "target": target})
            ],
            error=None,
        )
    for step in plan:
        backend._robot.send_action(step)
    return ExecutionResult(
        status="ok",
        trajectory=plan,
        events=[
            ExecutionEvent(
                kind="motion_complete",
                data={"capability": "arm.pick", "target": target},
            )
        ],
        error=None,
    )
