"""arm.pick: target descriptor → vision → extrinsic → IK → trajectory."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

import pytest

from robot_md.backends.feetech_depthai.capabilities import _arm_pick


def _so_arm101_fm():
    return {
        "physics": {
            "solver": {
                "convention": "DH",
                "base_frame": {"up": "z", "forward": "x"},
                "encoder": {"steps_per_rev": 4096},
                "gripper": {"joint_id": "gripper", "tip_offset_mm": [30, 0, 0], "open_steps": 1700, "close_steps": 1200},
                "ik_provider": "inhouse-so-arm101",
                "cameras": [
                    {"driver_id": "oakd", "primary_stream": "rgb", "mount": "world",
                     "extrinsic": [0, 0, 0, 0, 0, 0], "extrinsic_source": "preset_default"}
                ],
            },
            "kinematics": [
                {"id": "shoulder_pan", "axis": "z", "a_mm": 0, "d_mm": 60, "zero_pose_steps": 2048, "encoder_sign": 1},
                {"id": "shoulder_lift", "axis": "y", "a_mm": 125, "d_mm": 0, "zero_pose_steps": 2048, "encoder_sign": 1},
                {"id": "elbow_flex", "axis": "y", "a_mm": 125, "d_mm": 0, "zero_pose_steps": 2048, "encoder_sign": 1},
                {"id": "wrist_flex", "axis": "y", "a_mm": 60, "d_mm": 0, "zero_pose_steps": 2048, "encoder_sign": 1},
                {"id": "wrist_roll", "axis": "x", "a_mm": 0, "d_mm": 0, "zero_pose_steps": 2048, "encoder_sign": 1},
                {"id": "gripper", "axis": "y", "a_mm": 0, "d_mm": 0, "zero_pose_steps": 1200, "encoder_sign": 1},
            ],
            "workspace": {"bounds_mm": {"x": [-200, 340], "y": [-340, 340], "z": [0, 250]}},
        },
        "vision": {
            "object_descriptors": [
                {"id": "red_lego", "detector": "hsv", "params": {"h_ranges": [[0, 10]], "s_min": 110, "v_min": 80, "min_area": 500}}
            ]
        },
    }


@dataclass
class FakeBackend:
    raw_frontmatter: dict
    _servo_bus: Any = None
    _motion: Any = None
    _perception: Any = None
    _spec: Any = None


def _make_backend(*, vision_xyz=(100.0, 0.0, 50.0), bus_positions=None):
    fm = _so_arm101_fm()
    bus = MagicMock()
    bus.read_positions.return_value = bus_positions or {
        "shoulder_pan": 2048, "shoulder_lift": 2048, "elbow_flex": 2048,
        "wrist_flex": 2048, "wrist_roll": 2048, "gripper": 1700,
    }
    bus.torque = MagicMock()
    motion = MagicMock()
    perception = MagicMock()
    perception.vision_find.return_value = {"status": "ok", "descriptor": "red_lego", "xyz_cam_mm": vision_xyz}
    return FakeBackend(raw_frontmatter=fm, _servo_bus=bus, _motion=motion, _perception=perception)


def test_arm_pick_dry_run_returns_planned_trajectory():
    backend = _make_backend()
    result = _arm_pick(backend, args={"target": "red_lego"}, dry_run=True, estop=None)
    assert result.status == "ok", result.error
    assert result.trajectory is not None
    assert len(result.trajectory) >= 3


def test_arm_pick_blocks_when_descriptor_undeclared():
    backend = _make_backend()
    result = _arm_pick(backend, args={"target": "unknown_object"}, dry_run=True, estop=None)
    assert result.status == "blocked"
    assert result.error.get("reason") == "descriptor_not_declared"


def test_arm_pick_no_target_when_vision_finds_nothing():
    backend = _make_backend()
    backend._perception.vision_find.return_value = {"status": "no_match", "descriptor": "red_lego"}
    result = _arm_pick(backend, args={"target": "red_lego"}, dry_run=True, estop=None)
    assert result.status == "no_target"


def test_arm_pick_unreachable_when_target_outside_workspace():
    backend = _make_backend(vision_xyz=(900.0, 0.0, 0.0))
    result = _arm_pick(backend, args={"target": "red_lego"}, dry_run=True, estop=None)
    assert result.status == "unreachable"
    assert result.error.get("reason") == "outside_workspace"


def test_arm_pick_unreachable_when_ik_fails():
    # Target is inside the declared workspace (z ≤ 250) but the approach
    # point sits above the arm's reach envelope (L1+L2 = 250mm, plus L3
    # wrist/tool offset = 90mm shifts the wrist target further). Vertical
    # extension forces a 2-link overreach → IK raises KinematicsError →
    # planner re-raises → status="unreachable".
    backend = _make_backend(vision_xyz=(0.0, 0.0, 200.0))
    result = _arm_pick(backend, args={"target": "red_lego"}, dry_run=True, estop=None)
    assert result.status == "unreachable"
    assert result.error.get("reason") in ("ik_failed", "outside_workspace")


def test_arm_pick_defaults_approach_height_to_40mm():
    backend = _make_backend()
    result = _arm_pick(backend, args={"target": "red_lego"}, dry_run=True, estop=None)
    assert result.status == "ok", result.error
    plan_ev = next((e for e in result.events if e.kind == "plan"), None)
    assert plan_ev is not None
    assert plan_ev.data.get("approach_height_mm") == 40.0


def test_arm_pick_writes_to_bus_when_not_dry_run():
    backend = _make_backend()
    result = _arm_pick(backend, args={"target": "red_lego"}, dry_run=False, estop=None)
    assert result.status == "ok", result.error
    backend._motion.replay.assert_called_once()
