from __future__ import annotations

import pytest

from robot_md.backends.lerobot.config import build_lerobot_config
from robot_md.robot_spec import (
    DriverEntry,
    MetadataBlock,
    PhysicsBlock,
    RobotSpec,
    SafetyBlock,
    VisionBlock,
)


def _so_arm101_kinematics() -> tuple[dict, ...]:
    return (
        {
            "id": "shoulder_pan",
            "axis": "z",
            "limits_deg": [-180, 180],
            "length_mm": 60,
            "servo_id": 1,
            "encoder_sign": 1,
            "zero_pose_steps": 2048,
        },
        {
            "id": "shoulder_lift",
            "axis": "y",
            "limits_deg": [-90, 90],
            "length_mm": 125,
            "servo_id": 2,
            "encoder_sign": 1,
            "zero_pose_steps": 2048,
        },
        {
            "id": "elbow_flex",
            "axis": "y",
            "limits_deg": [-90, 90],
            "length_mm": 125,
            "servo_id": 3,
            "encoder_sign": 1,
            "zero_pose_steps": 2048,
        },
        {
            "id": "wrist_flex",
            "axis": "y",
            "limits_deg": [-90, 90],
            "length_mm": 60,
            "servo_id": 4,
            "encoder_sign": 1,
            "zero_pose_steps": 2048,
        },
        {
            "id": "wrist_roll",
            "axis": "x",
            "limits_deg": [-180, 180],
            "length_mm": 30,
            "servo_id": 5,
            "encoder_sign": 1,
            "zero_pose_steps": 2048,
        },
        {
            "id": "gripper",
            "axis": "y",
            "limits_deg": [0, 90],
            "length_mm": 40,
            "servo_id": 6,
            "encoder_sign": 1,
            "zero_pose_steps": 1200,
        },
    )


def _so_arm101_spec() -> RobotSpec:
    return RobotSpec(
        rcan_version="3.1",
        metadata=MetadataBlock(
            robot_name="bob",
            rrn="RRN-test-so-arm101",
            device_id=None,
            manufacturer=None,
            model=None,
            version=None,
            license=None,
        ),
        physics=PhysicsBlock(
            type="arm",
            dof=6,
            kinematics=_so_arm101_kinematics(),
            solver={},
            cameras=(),
            poses={},
            workspace=None,
        ),
        drivers=(
            DriverEntry(
                id="arm_servos",
                protocol="feetech",
                port="/dev/ttyACM0",
                baud_rate=1000000,
                model="STS3215",
                count=6,
                backend="lerobot",
                streams={},
            ),
        ),
        safety=SafetyBlock(
            max_joint_velocity_dps=None,
            max_linear_velocity_ms=None,
            payload_kg=None,
            workspace_bounds_m=None,
            failsafe_behavior=None,
            estop_software=False,
            estop_hardware=False,
            estop_response_ms=0,
            hitl_gates=(),
        ),
        capabilities=frozenset(),
        brain=None,
        raw_yaml="",
        capability_contracts={},
        vision=VisionBlock(object_descriptors=()),
        learned_skills=(),
    )


def test_build_config_extracts_six_motors() -> None:
    cfg = build_lerobot_config(_so_arm101_spec())
    assert cfg["robot_type"] == "so_arm"
    assert cfg["port"] == "/dev/ttyACM0"
    assert cfg["baud_rate"] == 1000000
    assert len(cfg["motors"]) == 6
    assert {m["joint"] for m in cfg["motors"]} == {
        "shoulder_pan",
        "shoulder_lift",
        "elbow_flex",
        "wrist_flex",
        "wrist_roll",
        "gripper",
    }
    # Each motor should carry its servo_id from kinematics and the driver's model.
    by_joint = {m["joint"]: m for m in cfg["motors"]}
    assert by_joint["shoulder_pan"]["servo_id"] == 1
    assert by_joint["gripper"]["servo_id"] == 6
    assert all(m["model"] == "STS3215" for m in cfg["motors"])


def test_build_config_no_arm_driver_raises() -> None:
    spec = _so_arm101_spec()
    # Replace the feetech driver with an unrelated one.
    bad = RobotSpec(
        rcan_version=spec.rcan_version,
        metadata=spec.metadata,
        physics=spec.physics,
        drivers=(
            DriverEntry(
                id="cam",
                protocol="usb",
                port=None,
                baud_rate=None,
                model=None,
                count=None,
                backend=None,
                streams={},
            ),
        ),
        safety=spec.safety,
        capabilities=spec.capabilities,
        brain=spec.brain,
        raw_yaml=spec.raw_yaml,
        capability_contracts=spec.capability_contracts,
        vision=spec.vision,
        learned_skills=spec.learned_skills,
    )
    with pytest.raises(ValueError) as exc:
        build_lerobot_config(bad)
    assert "feetech" in str(exc.value).lower() or "dynamixel" in str(exc.value).lower()


def test_build_config_no_kinematics_raises() -> None:
    spec = _so_arm101_spec()
    bad = RobotSpec(
        rcan_version=spec.rcan_version,
        metadata=spec.metadata,
        physics=PhysicsBlock(
            type=spec.physics.type,
            dof=spec.physics.dof,
            kinematics=(),  # empty
            solver=spec.physics.solver,
            cameras=spec.physics.cameras,
            poses=spec.physics.poses,
            workspace=spec.physics.workspace,
        ),
        drivers=spec.drivers,
        safety=spec.safety,
        capabilities=spec.capabilities,
        brain=spec.brain,
        raw_yaml=spec.raw_yaml,
        capability_contracts=spec.capability_contracts,
        vision=spec.vision,
        learned_skills=spec.learned_skills,
    )
    with pytest.raises(ValueError) as exc:
        build_lerobot_config(bad)
    error_msg = str(exc.value).lower()
    assert "kinematics" in error_msg or "joints" in error_msg or "motors" in error_msg
