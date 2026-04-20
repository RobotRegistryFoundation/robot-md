"""Capability dispatch for the feetech_depthai reference backend.

v0.6.1 pipeline for `arm.pick` / `arm.place`:

    target descriptor → Perception.vision_find → camera_to_base
    → workspace gate → Kinematics.ik_reach → plan_pick/plan_place
    → motion.replay (skipped on dry_run)

Returns structured `ExecutionResult(status, trajectory, events, error)` with
status ∈ {"ok", "blocked", "no_target", "unreachable", "error"} per the
v0.6.1 capability contract.
"""

from __future__ import annotations

from robot_md.backends.base import ExecutionEvent, ExecutionResult
from robot_md.backends.feetech_depthai.motion import Waypoint
from robot_md.extrinsic import camera_to_base
from robot_md.kinematics import Kinematics, KinematicsError
from robot_md.trajectory import plan_pick, plan_place


# ---------------------------------------------------------------- dispatch --


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


# ------------------------------------------------------- target-driven pick --


def _vision_xyz_cam(backend, descriptor_id: str):
    """Invoke Perception.vision_find. Returns (status, xyz_cam_mm | None, reason | None)."""
    if backend._perception is None:
        return ("error", None, "no_perception")
    try:
        res = backend._perception.vision_find(descriptor=descriptor_id)
    except Exception as e:
        return ("error", None, f"vision_error: {e}")
    status = res.get("status")
    if status == "ok":
        return ("ok", tuple(res["xyz_cam_mm"]), None)
    if status == "no_match":
        return ("no_target", None, f"{descriptor_id}_not_visible")
    return ("error", None, str(res.get("reason") or status or "vision_unknown_status"))


def _workspace_ok(fm: dict, xyz_base_mm) -> bool:
    ws = (fm.get("physics") or {}).get("workspace") or {}
    bounds = ws.get("bounds_mm")
    if not bounds:
        return True
    x, y, z = xyz_base_mm
    for axis, v in (("x", x), ("y", y), ("z", z)):
        rng = bounds.get(axis)
        if rng is None:
            continue
        lo, hi = rng
        if not (lo <= v <= hi):
            return False
    return True


def _descriptor_registered(fm: dict, descriptor_id: str) -> bool:
    descriptors = ((fm.get("vision") or {}).get("object_descriptors") or [])
    return any(d.get("id") == descriptor_id for d in descriptors)


def _get_extrinsic(fm: dict):
    cams = (fm.get("physics") or {}).get("solver", {}).get("cameras") or []
    if not cams:
        return None
    return cams[0].get("extrinsic")


def _execute_pick_or_place(
    *,
    backend,
    args,
    dry_run,
    estop,
    planner,
    default_approach_height_mm: float,
    label: str,
) -> ExecutionResult:
    fm = getattr(backend, "raw_frontmatter", None) or {}
    descriptor_id = args.get("target")
    if not isinstance(descriptor_id, str):
        return ExecutionResult(
            status="blocked",
            trajectory=None,
            events=[],
            error={"reason": "target_required", "label": label},
        )
    if not _descriptor_registered(fm, descriptor_id):
        return ExecutionResult(
            status="blocked",
            trajectory=None,
            events=[],
            error={"reason": "descriptor_not_declared", "descriptor": descriptor_id},
        )

    approach_height_mm = float(args.get("approach_height_mm", default_approach_height_mm))

    vstatus, xyz_cam, vreason = _vision_xyz_cam(backend, descriptor_id)
    if vstatus == "no_target":
        return ExecutionResult(
            status="no_target",
            trajectory=None,
            events=[],
            error={"reason": vreason, "descriptor": descriptor_id},
        )
    if vstatus == "error":
        return ExecutionResult(
            status="error",
            trajectory=None,
            events=[],
            error={"reason": vreason},
        )

    extrinsic = _get_extrinsic(fm)
    if extrinsic is None:
        return ExecutionResult(
            status="blocked",
            trajectory=None,
            events=[],
            error={"reason": "extrinsic_missing"},
        )
    xyz_base = camera_to_base(xyz_cam, extrinsic)

    if not _workspace_ok(fm, xyz_base):
        return ExecutionResult(
            status="unreachable",
            trajectory=None,
            events=[],
            error={"reason": "outside_workspace", "xyz_base_mm": xyz_base},
        )

    try:
        kin = Kinematics(fm)
    except KinematicsError as e:
        return ExecutionResult(
            status="error",
            trajectory=None,
            events=[],
            error={"reason": f"kinematics_init_failed: {e}"},
        )

    bus = backend._servo_bus
    try:
        start_joints = bus.read_positions() if bus is not None else {}
    except Exception as e:
        return ExecutionResult(
            status="error",
            trajectory=None,
            events=[],
            error={"reason": f"bus_error: {e}"},
        )
    if not start_joints:
        poses = (fm.get("physics") or {}).get("poses") or {}
        ready = (poses.get("ready") or {}).get("joints") or {}
        start_joints = dict(ready)

    try:
        waypoints = planner(
            start_joints=start_joints,
            target_base_xyz=xyz_base,
            approach_height_mm=approach_height_mm,
            kin=kin,
        )
    except KinematicsError as e:
        return ExecutionResult(
            status="unreachable",
            trajectory=None,
            events=[],
            error={"reason": "ik_failed", "detail": str(e)},
        )

    events = [
        ExecutionEvent(
            kind="plan",
            data={
                "capability": label,
                "descriptor": descriptor_id,
                "xyz_base_mm": xyz_base,
                "approach_height_mm": approach_height_mm,
                "waypoint_count": len(waypoints),
            },
        )
    ]
    trajectory = [{"phase": wp.phase, "joints": wp.joints} for wp in waypoints]

    if dry_run:
        events.append(ExecutionEvent(kind="done", data={"dry_run": True}))
        return ExecutionResult(status="ok", trajectory=trajectory, events=events, error=None)

    t = 0.0
    motion_waypoints: list[Waypoint] = []
    for wp in waypoints:
        motion_waypoints.append(Waypoint(t=t, joints=wp.joints))
        t += wp.settle_ms / 1000.0

    try:
        bus.torque(True)
        backend._motion.replay(motion_waypoints, servo_bus=bus, estop=estop)
    except Exception as e:
        events.append(ExecutionEvent(kind="bus_error", data={"detail": str(e)}))
        try:
            bus.torque(False)
        except Exception:
            pass
        return ExecutionResult(
            status="error",
            trajectory=trajectory,
            events=events,
            error={"reason": "bus_error", "detail": str(e)},
        )
    try:
        bus.torque(False)
    except Exception:
        pass

    events.append(ExecutionEvent(kind="done", data={"label": label}))
    return ExecutionResult(status="ok", trajectory=trajectory, events=events, error=None)


def _arm_pick(backend, *, args, dry_run, estop) -> ExecutionResult:
    return _execute_pick_or_place(
        backend=backend,
        args=args,
        dry_run=dry_run,
        estop=estop,
        planner=plan_pick,
        default_approach_height_mm=40.0,
        label="arm.pick",
    )


def _arm_place(backend, *, args, dry_run, estop) -> ExecutionResult:
    return _execute_pick_or_place(
        backend=backend,
        args=args,
        dry_run=dry_run,
        estop=estop,
        planner=plan_place,
        default_approach_height_mm=50.0,
        label="arm.place",
    )


# ------------------------------------------- arm.reach / arm.home / readers --


# Safe fallback joints used by arm.reach when no target is provided; all
# canonical joints at zero-pose steps with gripper open.
_REACH_DEFAULT_JOINTS = {
    "shoulder_pan": 2048,
    "shoulder_lift": 2048,
    "elbow_flex": 2048,
    "wrist_flex": 2048,
    "wrist_roll": 2048,
    "gripper": 1700,
}


def _do_replay(backend, *, waypoints, label, args, dry_run, estop) -> ExecutionResult:
    events: list[ExecutionEvent] = [
        ExecutionEvent(
            kind="plan",
            data={"capability": label, "args": args, "waypoint_count": len(waypoints)},
        ),
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


def _arm_reach(backend, *, args, dry_run, estop) -> ExecutionResult:
    wps = [Waypoint(t=0.0, joints=dict(_REACH_DEFAULT_JOINTS))]
    return _do_replay(
        backend, waypoints=wps, label="arm.reach", args=args, dry_run=dry_run, estop=estop
    )


def _home_joints(backend) -> dict[str, int]:
    """Resolve arm.home target joints.

    Prefers `physics.poses.ready` from the spec (Task 2 surfaced poses on
    RobotSpec). Falls back to the hardcoded zero pose so v0.5.0 manifests,
    which have no `physics.poses`, keep working.
    """
    base = {
        "shoulder_pan": 2048,
        "shoulder_lift": 2048,
        "elbow_flex": 2048,
        "wrist_flex": 2048,
        "wrist_roll": 2048,
        "gripper": 1700,
    }
    spec = getattr(backend, "_spec", None)
    if spec is None:
        return base
    physics = getattr(spec, "physics", None)
    poses = getattr(physics, "poses", None) if physics is not None else None
    if not poses:
        return base
    ready = poses.get("ready")
    if ready is None or not ready.joints:
        return base
    base.update({k: int(v) for k, v in ready.joints.items()})
    return base


def _arm_home(backend, *, args, dry_run, estop) -> ExecutionResult:
    wps = [Waypoint(t=0.0, joints=_home_joints(backend))]
    return _do_replay(
        backend, waypoints=wps, label="arm.home", args=args, dry_run=dry_run, estop=estop
    )


def _vision_describe(backend, *, args, dry_run, estop) -> ExecutionResult:
    if backend._perception is None:
        return ExecutionResult(
            status="error",
            trajectory=None,
            events=[],
            error={"reason": "no_perception"},
        )
    rgb, depth, _K = backend._perception.grab_frame()
    rgb_shape = tuple(rgb.shape) if hasattr(rgb, "shape") else None
    depth_shape = tuple(depth.shape) if hasattr(depth, "shape") else None
    return ExecutionResult(
        status="ok",
        trajectory=None,
        events=[
            ExecutionEvent(
                kind="frame",
                data={
                    "rgb_shape": rgb_shape,
                    "depth_shape": depth_shape,
                },
            )
        ],
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
    "arm.home": _arm_home,
    "vision.describe": _vision_describe,
    "status.report": _status_report,
}
