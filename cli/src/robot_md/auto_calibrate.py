"""Compute a canonical `ready` pose from DH parameters via the baseline IK solver.

Used by the `phase_auto_calibrate_ready` init phase. Pure function — no I/O.
Returns `None` when IK reports the target is unreachable; callers surface the
reason via their own logging.
"""

from __future__ import annotations

from typing import Any

from robot_md.kinematics import Kinematics, KinematicsError


def compute_ready_pose(
    parsed: Any,
    *,
    target_mm: tuple[float, float, float] = (200.0, 0.0, 50.0),
) -> dict[str, int] | None:
    """Solve IK for `target_mm` and return per-joint encoder step targets.

    Includes wrist_roll (zero angle) and gripper (open_steps) so the
    returned dict is a complete pose usable by `arm.home`.
    """
    try:
        kin = Kinematics(parsed)
    except KinematicsError:
        return None
    try:
        angles = kin.ik_reach(target_mm)
    except KinematicsError:
        return None

    angles.setdefault("wrist_roll", 0.0)
    steps = kin.angles_to_step_targets(angles)

    gripper_open = None
    solver = (parsed.get("physics") or {}).get("solver") or {}
    grip = solver.get("gripper") or {}
    if "open_steps" in grip:
        gripper_open = int(grip["open_steps"])
    if gripper_open is not None:
        steps["gripper"] = gripper_open
    return steps
