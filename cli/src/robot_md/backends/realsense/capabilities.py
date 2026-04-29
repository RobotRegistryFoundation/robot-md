"""RealSense capability dispatch."""

from __future__ import annotations

from robot_md.backends.base import ExecutionResult
from robot_md.backends.realsense.perception import perceive_depth, perceive_rgb

HANDLERS = {
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
