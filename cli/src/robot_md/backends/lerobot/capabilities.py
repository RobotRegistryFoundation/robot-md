"""LeRobot capability dispatch — populated incrementally."""

from __future__ import annotations

from robot_md.backends.base import ExecutionResult


def dispatch(backend, *, capability: str, args: dict, dry_run: bool, estop) -> ExecutionResult:
    return ExecutionResult(
        status="error",
        trajectory=None,
        events=[],
        error={"reason": "not_implemented", "detail": f"capability {capability!r}"},
    )
