"""LeRobot capability dispatch — populated incrementally."""

from __future__ import annotations

from robot_md.backends.base import ExecutionResult
from robot_md.backends.lerobot.motion import (
    arm_home,
    arm_pick,
    arm_place,
    gripper_close,
    gripper_open,
)
from robot_md.backends.lerobot.perception import perceive_depth, perceive_rgb

HANDLERS = {
    "arm.pick": arm_pick,
    "arm.place": arm_place,
    "arm.home": arm_home,
    "gripper.open": gripper_open,
    "gripper.close": gripper_close,
    "perceive.rgb": perceive_rgb,
    "perceive.depth": perceive_depth,
}


def dispatch(backend, *, capability: str, args: dict, dry_run: bool, estop) -> ExecutionResult:
    handler = HANDLERS.get(capability)
    if handler is None:
        return ExecutionResult(
            status="error",
            trajectory=None,
            events=[],
            error={"reason": "not_implemented", "detail": f"capability {capability!r}"},
        )
    return handler(backend, args, dry_run=dry_run, estop=estop)
