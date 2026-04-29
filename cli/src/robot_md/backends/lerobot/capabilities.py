"""LeRobot capability dispatch — populated incrementally."""

from __future__ import annotations

from robot_md.backends.base import ExecutionResult
from robot_md.backends.lerobot.motion import arm_pick

HANDLERS = {
    "arm.pick": arm_pick,
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
