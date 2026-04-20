"""plan_pick / plan_place: hybrid trajectory generator."""
from __future__ import annotations

import math

import pytest

from robot_md.kinematics import Kinematics
from robot_md.trajectory import plan_pick, plan_place


def _fm():
    return {
        "physics": {
            "solver": {
                "convention": "DH",
                "base_frame": {"up": "z", "forward": "x"},
                "encoder": {"steps_per_rev": 4096},
                "gripper": {
                    "joint_id": "gripper",
                    "tip_offset_mm": [30, 0, 0],
                    "open_steps": 1700,
                    "close_steps": 1200,
                },
            },
            "kinematics": [
                {"id": "shoulder_pan", "axis": "z", "a_mm": 0, "d_mm": 60, "zero_pose_steps": 2048, "encoder_sign": 1},
                {"id": "shoulder_lift", "axis": "y", "a_mm": 125, "d_mm": 0, "zero_pose_steps": 2048, "encoder_sign": 1},
                {"id": "elbow_flex", "axis": "y", "a_mm": 125, "d_mm": 0, "zero_pose_steps": 2048, "encoder_sign": 1},
                {"id": "wrist_flex", "axis": "y", "a_mm": 60, "d_mm": 0, "zero_pose_steps": 2048, "encoder_sign": 1},
                {"id": "wrist_roll", "axis": "x", "a_mm": 0, "d_mm": 0, "zero_pose_steps": 2048, "encoder_sign": 1},
                {"id": "gripper", "axis": "y", "a_mm": 0, "d_mm": 0, "zero_pose_steps": 1200, "encoder_sign": 1},
            ],
        }
    }


def test_plan_pick_has_approach_descent_grasp_lift_phases():
    kin = Kinematics(_fm())
    start = {"shoulder_pan": 2048, "shoulder_lift": 2048, "elbow_flex": 2048, "wrist_flex": 2048, "wrist_roll": 2048, "gripper": 1700}
    wps = plan_pick(start_joints=start, target_base_xyz=(200, 0, 50), approach_height_mm=40, kin=kin, descent_slices=5)
    # 1 approach + 5 descent (including grasp point) + 1 grasp-close + 1 lift = 8
    assert len(wps) == 8
    phases = [wp.phase for wp in wps]
    assert phases == ["approach", "descent", "descent", "descent", "descent", "descent", "grasp_close", "lift"]


def test_plan_pick_approach_waypoint_is_above_target():
    kin = Kinematics(_fm())
    start = {"shoulder_pan": 2048, "shoulder_lift": 2048, "elbow_flex": 2048, "wrist_flex": 2048, "wrist_roll": 2048, "gripper": 1700}
    wps = plan_pick(start_joints=start, target_base_xyz=(200, 0, 50), approach_height_mm=40, kin=kin, descent_slices=5)
    approach = wps[0]
    angles = kin.steps_to_angles({k: v for k, v in approach.joints.items() if k in kin.by_id})
    x, y, z = kin.fk(angles)
    assert (x, y, z) == pytest.approx((200, 0, 90), abs=5.0)


def test_plan_pick_descent_is_linear_in_base_z():
    kin = Kinematics(_fm())
    start = {"shoulder_pan": 2048, "shoulder_lift": 2048, "elbow_flex": 2048, "wrist_flex": 2048, "wrist_roll": 2048, "gripper": 1700}
    wps = plan_pick(start_joints=start, target_base_xyz=(200, 0, 50), approach_height_mm=40, kin=kin, descent_slices=5)
    descent_wps = [w for w in wps if w.phase == "descent"]
    zs = []
    for w in descent_wps:
        angles = kin.steps_to_angles({k: v for k, v in w.joints.items() if k in kin.by_id})
        _, _, z = kin.fk(angles)
        zs.append(z)
    for a, b in zip(zs, zs[1:]):
        assert a > b
    assert zs[-1] == pytest.approx(50, abs=5.0)


def test_plan_pick_grasp_close_changes_gripper_only():
    kin = Kinematics(_fm())
    start = {"shoulder_pan": 2048, "shoulder_lift": 2048, "elbow_flex": 2048, "wrist_flex": 2048, "wrist_roll": 2048, "gripper": 1700}
    wps = plan_pick(start_joints=start, target_base_xyz=(200, 0, 50), approach_height_mm=40, kin=kin, descent_slices=5)
    last_descent = [w for w in wps if w.phase == "descent"][-1]
    grasp = next(w for w in wps if w.phase == "grasp_close")
    for k in ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll"):
        assert grasp.joints[k] == last_descent.joints[k]
    assert grasp.joints["gripper"] == 1200


def test_plan_pick_lift_returns_to_approach_height():
    kin = Kinematics(_fm())
    start = {"shoulder_pan": 2048, "shoulder_lift": 2048, "elbow_flex": 2048, "wrist_flex": 2048, "wrist_roll": 2048, "gripper": 1700}
    wps = plan_pick(start_joints=start, target_base_xyz=(200, 0, 50), approach_height_mm=40, kin=kin, descent_slices=5)
    lift = wps[-1]
    angles = kin.steps_to_angles({k: v for k, v in lift.joints.items() if k in kin.by_id})
    x, y, z = kin.fk(angles)
    assert z == pytest.approx(90, abs=5.0)
    assert lift.joints["gripper"] == 1200


def test_plan_place_opens_gripper_at_bottom():
    kin = Kinematics(_fm())
    start = {"shoulder_pan": 2048, "shoulder_lift": 2048, "elbow_flex": 2048, "wrist_flex": 2048, "wrist_roll": 2048, "gripper": 1200}
    wps = plan_place(start_joints=start, target_base_xyz=(180, 80, 60), approach_height_mm=50, kin=kin, descent_slices=5)
    release = next(w for w in wps if w.phase == "grasp_open")
    assert release.joints["gripper"] == 1700
