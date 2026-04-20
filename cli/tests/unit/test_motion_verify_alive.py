"""Post-motion watchdog detects dropped servos and contains damage."""
from __future__ import annotations

from unittest.mock import MagicMock

from robot_md.backends.feetech_depthai.motion import AliveReport, Motion
from robot_md.parser import parse_file
from robot_md.robot_spec import RobotSpec


def _spec(fixtures_dir):
    return RobotSpec.from_parsed(parse_file(fixtures_dir / "robot_md_oak_d_factory_cal.yaml"))


def test_verify_alive_all_present(fixtures_dir):
    motion = Motion.from_spec(_spec(fixtures_dir))
    bus = MagicMock()
    bus.read_positions.return_value = {
        "shoulder_pan": 2048,
        "shoulder_lift": 2048,
        "elbow_flex": 2048,
        "wrist_flex": 2048,
        "wrist_roll": 2048,
        "gripper": 1700,
    }
    expected = {"shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"}
    report = motion.verify_alive(bus, expected_ids=expected)
    assert isinstance(report, AliveReport)
    assert report.alive is True
    assert report.missing == []
    bus.torque.assert_not_called()


def test_verify_alive_detects_missing_servo_and_torques_off_remaining(fixtures_dir):
    motion = Motion.from_spec(_spec(fixtures_dir))
    bus = MagicMock()
    # wrist_flex dropped (latched + stopped responding on bus).
    bus.read_positions.return_value = {
        "shoulder_pan": 2048,
        "shoulder_lift": 2048,
        "elbow_flex": 2048,
        "wrist_roll": 2048,
        "gripper": 1700,
    }
    expected = {"shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"}
    report = motion.verify_alive(bus, expected_ids=expected)
    assert report.alive is False
    assert report.missing == ["wrist_flex"]
    # Safety: torque off remaining servos to prevent cascade damage.
    bus.torque.assert_called_once_with(False)


def test_verify_alive_multiple_missing(fixtures_dir):
    motion = Motion.from_spec(_spec(fixtures_dir))
    bus = MagicMock()
    bus.read_positions.return_value = {"shoulder_pan": 2048, "gripper": 1700}
    expected = {"shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"}
    report = motion.verify_alive(bus, expected_ids=expected)
    assert report.alive is False
    assert set(report.missing) == {"shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll"}
    bus.torque.assert_called_once_with(False)


def test_verify_alive_bus_exception_torques_off_and_reports_all_missing(fixtures_dir):
    """When the bus itself fails (read_positions raises), verify_alive
    treats every expected servo as missing, torques off the bus, and
    returns alive=False. This is the worst-case path and must leave the
    arm in a safe state."""
    motion = Motion.from_spec(_spec(fixtures_dir))
    bus = MagicMock()
    bus.read_positions.side_effect = RuntimeError("bus timeout")
    expected = {"shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"}
    report = motion.verify_alive(bus, expected_ids=expected)
    assert report.alive is False
    assert set(report.missing) == expected
    assert report.missing == sorted(report.missing)  # sort-order contract
    bus.torque.assert_called_once_with(False)
