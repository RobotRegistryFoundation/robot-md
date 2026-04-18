"""Capability dispatch: arm.pick / arm.place / arm.reach / vision.describe / status.report.

Phase 1 scope: `arm.pick` and `arm.place` replay a hardcoded first-demo
trajectory. Skill-store lookup arrives in Phase 2.
"""

from __future__ import annotations

from robot_md.backends.base import ExecutionEvent, ExecutionResult
from robot_md.backends.feetech_depthai.motion import Waypoint

# Hardcoded first-demo waypoints around zero-pose (2048 arm joints; gripper 1700 open / 1200 closed).
_ZERO = {
    "shoulder_pan": 2048, "shoulder_lift": 2048, "elbow_flex": 2048,
    "wrist_flex": 2048, "wrist_roll": 2048,
}
_PICK_OPEN = {**_ZERO, "gripper": 1700}
_PICK_CLOSED = {**_ZERO, "gripper": 1200}
_PICK_LIFTED = {**_ZERO, "shoulder_lift": 1928, "gripper": 1200}  # 120 steps up

_HARDCODED_PICK_WAYPOINTS: list[Waypoint] = [
    Waypoint(t=0.0, joints=_PICK_OPEN),
    Waypoint(t=0.5, joints=_PICK_OPEN),
    Waypoint(t=1.1, joints=_PICK_CLOSED),
    Waypoint(t=1.7, joints=_PICK_LIFTED),
]

_PLACE_LEFT = {**_ZERO, "shoulder_pan": 2148}
_PLACE_LEFT_LIFTED = {**_PLACE_LEFT, "shoulder_lift": 1928, "gripper": 1200}
_PLACE_LEFT_DOWN = {**_PLACE_LEFT, "gripper": 1200}
_PLACE_LEFT_RELEASE = {**_PLACE_LEFT, "gripper": 1700}

_HARDCODED_PLACE_WAYPOINTS: list[Waypoint] = [
    Waypoint(t=0.0, joints=_PICK_LIFTED),
    Waypoint(t=0.7, joints=_PLACE_LEFT_LIFTED),
    Waypoint(t=1.3, joints=_PLACE_LEFT_DOWN),
    Waypoint(t=1.8, joints=_PLACE_LEFT_RELEASE),
    Waypoint(t=2.4, joints=_PICK_OPEN),
]


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


def _do_replay(backend, *, waypoints, label, args, dry_run, estop) -> ExecutionResult:
    events: list[ExecutionEvent] = [
        ExecutionEvent(kind="plan", data={"capability": label, "args": args,
                                           "waypoint_count": len(waypoints)}),
    ]
    trajectory = [{"t": wp.t, "joints": wp.joints} for wp in waypoints]

    if dry_run:
        events.append(ExecutionEvent(kind="done", data={"dry_run": True}))
        return ExecutionResult(status="ok", trajectory=trajectory, events=events, error=None)

    bus = backend._servo_bus
    motion = backend._motion
    try:
        bus.torque(True)
        motion.replay(waypoints, servo_bus=bus, estop=estop)
    finally:
        bus.torque(False)

    events.append(ExecutionEvent(kind="done", data={"label": label}))
    return ExecutionResult(status="ok", trajectory=trajectory, events=events, error=None)


def _arm_pick(backend, *, args, dry_run, estop) -> ExecutionResult:
    return _do_replay(backend, waypoints=_HARDCODED_PICK_WAYPOINTS,
                      label="arm.pick", args=args, dry_run=dry_run, estop=estop)


def _arm_place(backend, *, args, dry_run, estop) -> ExecutionResult:
    return _do_replay(backend, waypoints=_HARDCODED_PLACE_WAYPOINTS,
                      label="arm.place", args=args, dry_run=dry_run, estop=estop)


def _arm_reach(backend, *, args, dry_run, estop) -> ExecutionResult:
    wps = [Waypoint(t=0.0, joints=_PICK_OPEN)]
    return _do_replay(backend, waypoints=wps,
                      label="arm.reach", args=args, dry_run=dry_run, estop=estop)


def _vision_describe(backend, *, args, dry_run, estop) -> ExecutionResult:
    if backend._perception is None:
        return ExecutionResult(
            status="error", trajectory=None, events=[],
            error={"reason": "no_perception"},
        )
    rgb, depth, K = backend._perception.grab_frame()
    rgb_shape = tuple(rgb.shape) if hasattr(rgb, "shape") else None
    depth_shape = tuple(depth.shape) if hasattr(depth, "shape") else None
    return ExecutionResult(
        status="ok",
        trajectory=None,
        events=[ExecutionEvent(kind="frame", data={
            "rgb_shape": rgb_shape, "depth_shape": depth_shape,
        })],
        error=None,
    )


def _status_report(backend, *, args, dry_run, estop) -> ExecutionResult:
    robot_name = ""
    if backend._spec is not None:
        robot_name = backend._spec.metadata.robot_name
    joints = backend._servo_bus.read_positions() if backend._servo_bus is not None else {}
    return ExecutionResult(
        status="ok",
        trajectory=None,
        events=[ExecutionEvent(kind="done", data={"robot": robot_name, "joints": joints})],
        error=None,
    )


_HANDLERS = {
    "arm.pick": _arm_pick,
    "arm.place": _arm_place,
    "arm.reach": _arm_reach,
    "vision.describe": _vision_describe,
    "status.report": _status_report,
}
