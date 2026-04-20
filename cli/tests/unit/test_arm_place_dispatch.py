# cli/tests/unit/test_arm_place_dispatch.py
"""arm.place: same pipeline as arm.pick but gripper opens at target."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

import pytest

from robot_md.backends.feetech_depthai.capabilities import _arm_place


def _fm_with_bowl():
    return {
        "physics": {
            "solver": {
                "convention": "DH",
                "base_frame": {"up": "z", "forward": "x"},
                "encoder": {"steps_per_rev": 4096},
                "gripper": {"joint_id": "gripper", "tip_offset_mm": [30, 0, 0], "open_steps": 1700, "close_steps": 1200},
                "ik_provider": "inhouse-so-arm101",
                "cameras": [{"driver_id": "oakd", "primary_stream": "rgb", "mount": "world",
                              "extrinsic": [0, 0, 0, 0, 0, 0]}],
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
        "vision": {"object_descriptors": [{"id": "white_bowl", "detector": "hsv_roi", "params": {}}]},
    }


@dataclass
class _B:
    raw_frontmatter: dict
    _servo_bus: Any
    _motion: Any
    _perception: Any
    _spec: Any = None


def _make_backend():
    fm = _fm_with_bowl()
    bus = MagicMock()
    bus.read_positions.return_value = {"shoulder_pan": 2048, "shoulder_lift": 2048, "elbow_flex": 2048, "wrist_flex": 2048, "wrist_roll": 2048, "gripper": 1200}
    bus.torque = MagicMock()
    motion = MagicMock()
    perception = MagicMock()
    perception.vision_find.return_value = {"status": "ok", "descriptor": "white_bowl", "xyz_cam_mm": (150.0, 60.0, 40.0)}
    return _B(raw_frontmatter=fm, _servo_bus=bus, _motion=motion, _perception=perception)


def test_arm_place_dry_run_ok():
    backend = _make_backend()
    result = _arm_place(backend, args={"target": "white_bowl"}, dry_run=True, estop=None)
    assert result.status == "ok", result.error
    phases = [wp["phase"] for wp in result.trajectory]
    assert "grasp_open" in phases


def test_arm_place_default_approach_height_is_50():
    backend = _make_backend()
    result = _arm_place(backend, args={"target": "white_bowl"}, dry_run=True, estop=None)
    plan_ev = next(e for e in result.events if e.kind == "plan")
    assert plan_ev.data["approach_height_mm"] == 50.0


def test_arm_place_blocks_on_unknown_target():
    backend = _make_backend()
    result = _arm_place(backend, args={"target": "mystery_object"}, dry_run=True, estop=None)
    assert result.status == "blocked"
    assert result.error["reason"] == "descriptor_not_declared"
