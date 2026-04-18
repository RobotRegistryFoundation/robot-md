"""Capability dispatch: arm.pick/place/reach, vision.describe, status.report."""

from __future__ import annotations

from robot_md.backends.base import ExecutionEvent, ExecutionResult


def dispatch(backend, *, capability: str, args: dict, dry_run: bool, estop) -> ExecutionResult:
    handler = _HANDLERS.get(capability)
    if handler is None:
        return ExecutionResult(
            status="error",
            trajectory=None,
            events=[],
            error={"reason": "not_implemented", "capability": capability},
        )
    return handler(backend, args=args, dry_run=dry_run, estop=estop)


def _arm_pick(backend, *, args, dry_run, estop) -> ExecutionResult:
    return ExecutionResult(
        status="ok",
        trajectory=[{"t": 0.0, "joints": {}}],
        events=[ExecutionEvent(kind="plan", data={"capability": "arm.pick", "args": args})],
        error=None,
    )


def _arm_place(backend, *, args, dry_run, estop) -> ExecutionResult:
    return ExecutionResult(
        status="ok",
        trajectory=[{"t": 0.0, "joints": {}}],
        events=[ExecutionEvent(kind="plan", data={"capability": "arm.place", "args": args})],
        error=None,
    )


def _arm_reach(backend, *, args, dry_run, estop) -> ExecutionResult:
    return ExecutionResult(
        status="ok",
        trajectory=[{"t": 0.0, "joints": {}}],
        events=[ExecutionEvent(kind="plan", data={"capability": "arm.reach", "args": args})],
        error=None,
    )


def _vision_describe(backend, *, args, dry_run, estop) -> ExecutionResult:
    snap = backend.scene_describe()
    return ExecutionResult(
        status="ok",
        trajectory=None,
        events=[ExecutionEvent(kind="frame", data={"detections": list(snap.detections)})],
        error=None,
    )


def _status_report(backend, *, args, dry_run, estop) -> ExecutionResult:
    robot_name = ""
    if backend._spec is not None:
        robot_name = backend._spec.metadata.robot_name
    return ExecutionResult(
        status="ok",
        trajectory=None,
        events=[ExecutionEvent(kind="done", data={"robot": robot_name})],
        error=None,
    )


_HANDLERS = {
    "arm.pick": _arm_pick,
    "arm.place": _arm_place,
    "arm.reach": _arm_reach,
    "vision.describe": _vision_describe,
    "status.report": _status_report,
}
