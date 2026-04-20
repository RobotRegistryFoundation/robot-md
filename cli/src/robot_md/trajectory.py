"""Plan hybrid pick/place trajectories.

Hybrid strategy: joint-space to approach pose, cartesian linear descent
(IK at N slices), gripper close/open at target, joint-space lift.

Pure functions. No I/O. The backend executes the resulting waypoints.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from robot_md.kinematics import Kinematics, KinematicsError


@dataclass(frozen=True)
class Waypoint:
    phase: str  # "approach" | "descent" | "grasp_close" | "grasp_open" | "lift"
    joints: dict[str, int]
    settle_ms: int = 300


def _solve_and_fill(kin: Kinematics, target_xyz, base_joints: dict[str, int]) -> dict[str, int]:
    """IK at target -> per-joint steps, padded with untouched joints from base."""
    angles = kin.ik_reach(target_xyz)
    angles.setdefault("wrist_roll", 0.0)
    steps = kin.angles_to_step_targets(angles)
    for k, v in base_joints.items():
        steps.setdefault(k, v)
    return steps


def _plan_core(
    *,
    start_joints: dict[str, int],
    target_base_xyz,
    approach_height_mm: float,
    kin: Kinematics,
    descent_slices: int,
    gripper_approach: int,
    gripper_bottom: int,
    gripper_bottom_phase: str,
    gripper_lift: int,
    hold_ms: int = 1000,
) -> list[Waypoint]:
    if descent_slices < 1:
        raise ValueError("descent_slices must be >= 1")
    tx, ty, tz = target_base_xyz
    approach_xyz = (tx, ty, tz + approach_height_mm)

    approach_steps = _solve_and_fill(kin, approach_xyz, start_joints)
    approach_steps["gripper"] = gripper_approach
    waypoints: list[Waypoint] = [Waypoint(phase="approach", joints=approach_steps)]

    prev = approach_steps
    for i in range(descent_slices):
        frac = (i + 1) / descent_slices
        z_slice = approach_xyz[2] + (tz - approach_xyz[2]) * frac
        slice_xyz = (tx, ty, z_slice)
        try:
            slice_steps = _solve_and_fill(kin, slice_xyz, prev)
        except KinematicsError:
            break
        slice_steps["gripper"] = gripper_approach
        waypoints.append(Waypoint(phase="descent", joints=slice_steps))
        prev = slice_steps

    # Pre-flight envelope check at the grasp/place pose — this is the config
    # held under load for hold_ms.  Convert steps back to angles for analysis.
    grasp_angles = kin.steps_to_angles({k: v for k, v in prev.items() if k in kin.by_id})
    risk = kin.analyze_envelope(grasp_angles, duration_ms=hold_ms)
    if risk.level == "out_of_limits":
        raise KinematicsError(f"ik solution out of limits: {risk.reason}")
    if risk.level == "latch_warning":
        raise KinematicsError(f"ik solution at latch_warning: {risk.reason}")

    bottom_steps = {**prev, "gripper": gripper_bottom}
    waypoints.append(Waypoint(phase=gripper_bottom_phase, joints=bottom_steps))

    lift_steps = {**approach_steps, "gripper": gripper_lift}
    waypoints.append(Waypoint(phase="lift", joints=lift_steps))
    return waypoints


def plan_pick(
    *,
    start_joints: dict[str, int],
    target_base_xyz,
    approach_height_mm: float,
    kin: Kinematics,
    descent_slices: int = 5,
    hold_ms: int = 1000,
) -> list[Waypoint]:
    """Pick: approach (gripper open) -> descent (open) -> close -> lift (closed).

    ``hold_ms`` is the duration the arm will hold the grasp pose under load.
    Passed to ``analyze_envelope`` to detect STS3215 latch risk before
    returning the plan.  Default 1000ms matches a typical grasp hold.
    """
    grip = kin.gripper_open_steps if kin.gripper_open_steps is not None else 1700
    close = kin.gripper_close_steps if kin.gripper_close_steps is not None else 1200
    return _plan_core(
        start_joints=start_joints,
        target_base_xyz=target_base_xyz,
        approach_height_mm=approach_height_mm,
        kin=kin,
        descent_slices=descent_slices,
        gripper_approach=grip,
        gripper_bottom=close,
        gripper_bottom_phase="grasp_close",
        gripper_lift=close,
        hold_ms=hold_ms,
    )


def plan_place(
    *,
    start_joints: dict[str, int],
    target_base_xyz,
    approach_height_mm: float,
    kin: Kinematics,
    descent_slices: int = 5,
    hold_ms: int = 1000,
) -> list[Waypoint]:
    """Place: approach (gripper closed) -> descent (closed) -> open -> lift (open).

    ``hold_ms`` is the duration the arm holds the place pose under load.
    Passed to ``analyze_envelope`` to detect STS3215 latch risk before
    returning the plan.  Default 1000ms matches a typical place hold.
    """
    grip_open = kin.gripper_open_steps if kin.gripper_open_steps is not None else 1700
    grip_closed = kin.gripper_close_steps if kin.gripper_close_steps is not None else 1200
    return _plan_core(
        start_joints=start_joints,
        target_base_xyz=target_base_xyz,
        approach_height_mm=approach_height_mm,
        kin=kin,
        descent_slices=descent_slices,
        gripper_approach=grip_closed,
        gripper_bottom=grip_open,
        gripper_bottom_phase="grasp_open",
        gripper_lift=grip_open,
        hold_ms=hold_ms,
    )
