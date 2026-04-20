"""Hardware-state checks for feetech+depthai backend."""
from __future__ import annotations

from unittest.mock import MagicMock

from robot_md.backends.feetech_depthai.doctor import hw_checks


def test_hw_checks_ok_when_full_enumeration_and_streams():
    bus = MagicMock()
    bus.read_positions.return_value = {
        "shoulder_pan": 2048, "shoulder_lift": 2048, "elbow_flex": 2048,
        "wrist_flex": 2048, "wrist_roll": 2048, "gripper": 1700,
    }
    camera = MagicMock()
    camera.probe.return_value = {"rgb": True, "depth": True}
    expected_ids = {"shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"}

    checks = hw_checks(bus=bus, camera=camera, expected_servo_ids=expected_ids)
    names = [c.name for c in checks]
    assert "servo_enumeration" in names
    assert "rgb_stream" in names
    assert "depth_stream" in names
    assert all(c.status == "pass" for c in checks)


def test_hw_checks_warn_on_servo_count_mismatch():
    bus = MagicMock()
    bus.read_positions.return_value = {
        "shoulder_pan": 2048, "shoulder_lift": 2048, "elbow_flex": 2048,
        # wrist_flex missing (latched or unplugged).
        "wrist_roll": 2048, "gripper": 1700,
    }
    camera = MagicMock()
    camera.probe.return_value = {"rgb": True, "depth": True}
    expected_ids = {"shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"}

    checks = hw_checks(bus=bus, camera=camera, expected_servo_ids=expected_ids)
    servo_check = next(c for c in checks if c.name == "servo_enumeration")
    assert servo_check.status == "warn"
    assert "wrist_flex" in servo_check.message


def test_hw_checks_error_on_missing_depth_stream():
    bus = MagicMock()
    bus.read_positions.return_value = {}
    camera = MagicMock()
    camera.probe.return_value = {"rgb": True, "depth": False}

    checks = hw_checks(bus=bus, camera=camera, expected_servo_ids=set())
    depth_check = next(c for c in checks if c.name == "depth_stream")
    assert depth_check.status == "error"
