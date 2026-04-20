"""compute_ready_pose: IK-based joint-step computation from DH params."""
from __future__ import annotations

import math

import pytest

from robot_md.auto_calibrate import compute_ready_pose
from robot_md.kinematics import Kinematics


def _so_arm101_frontmatter():
    """Minimal DH description matching the so_arm101 preset."""
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
                "ik_provider": "inhouse-so-arm101",
            },
            "kinematics": [
                {"id": "shoulder_pan", "axis": "z", "a_mm": 0, "d_mm": 60, "zero_pose_steps": 2048, "encoder_sign": 1},
                {"id": "shoulder_lift", "axis": "y", "a_mm": 125, "d_mm": 0, "zero_pose_steps": 2048, "encoder_sign": 1},
                {"id": "elbow_flex", "axis": "y", "a_mm": 125, "d_mm": 0, "zero_pose_steps": 2048, "encoder_sign": 1},
                {"id": "wrist_flex", "axis": "y", "a_mm": 60, "d_mm": 0, "zero_pose_steps": 2048, "encoder_sign": 1},
                {"id": "wrist_roll", "axis": "x", "a_mm": 30, "d_mm": 0, "zero_pose_steps": 2048, "encoder_sign": 1},
                {"id": "gripper", "axis": "y", "a_mm": 0, "d_mm": 0, "zero_pose_steps": 1200, "encoder_sign": 1},
            ],
        }
    }


def test_compute_ready_pose_returns_all_joint_ids():
    steps = compute_ready_pose(_so_arm101_frontmatter(), target_mm=(200, 0, 50))
    assert steps is not None
    assert set(steps.keys()) >= {"shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"}
    for v in steps.values():
        assert isinstance(v, int)


def test_compute_ready_pose_fk_lands_at_target_within_tolerance():
    """Round-trip: IK then FK should land near the requested target."""
    fm = _so_arm101_frontmatter()
    target = (200, 0, 50)
    steps = compute_ready_pose(fm, target_mm=target)
    assert steps is not None
    kin = Kinematics(fm)
    angles = kin.steps_to_angles({k: v for k, v in steps.items() if k in kin.by_id})
    x, y, z = kin.fk(angles)
    assert (x, y, z) == pytest.approx(target, abs=5.0)


def test_compute_ready_pose_returns_none_when_unreachable():
    """Target 2 meters away on a 340mm arm -> unreachable."""
    steps = compute_ready_pose(_so_arm101_frontmatter(), target_mm=(2000, 0, 0))
    assert steps is None


def test_compute_ready_pose_gripper_defaults_to_open():
    steps = compute_ready_pose(_so_arm101_frontmatter(), target_mm=(200, 0, 50))
    assert steps is not None
    assert steps["gripper"] == 1700


def test_compute_ready_pose_uses_default_target_when_omitted():
    """Default target is (200, 0, 20) mm — keeps wrist_flex well inside the
    ±90° declared limit on SO-ARM101 (was (200, 0, 50) but that produced
    wrist_flex=94.7°, beyond the servo's mechanical envelope)."""
    a = compute_ready_pose(_so_arm101_frontmatter())
    b = compute_ready_pose(_so_arm101_frontmatter(), target_mm=(200, 0, 20))
    assert a == b
