from __future__ import annotations

from unittest.mock import MagicMock

from robot_md.backends.feetech_depthai.motion import Motion, Waypoint
from robot_md.parser import parse_file
from robot_md.robot_spec import RobotSpec


def _spec(fixtures_dir):
    return RobotSpec.from_parsed(parse_file(fixtures_dir / "robot_md_oak_d_factory_cal.yaml"))


def test_replay_calls_interpolate_per_segment(fixtures_dir):
    motion = Motion.from_spec(_spec(fixtures_dir))
    bus = MagicMock()
    estop = MagicMock()
    estop.is_set.return_value = False

    wp0 = Waypoint(
        t=0.0,
        joints={
            "shoulder_pan": 2048,
            "shoulder_lift": 2048,
            "elbow_flex": 2048,
            "wrist_flex": 2048,
            "wrist_roll": 2048,
            "gripper": 1700,
        },
    )
    wp1 = Waypoint(t=0.5, joints={**wp0.joints, "shoulder_pan": 2100})
    wp2 = Waypoint(t=1.0, joints={**wp1.joints, "gripper": 1200})

    motion.replay([wp0, wp1, wp2], servo_bus=bus, estop=estop)
    assert bus.interpolate.call_count == 2
    first_call = bus.interpolate.call_args_list[0]
    assert first_call.args[0] == wp0.joints
    assert first_call.args[1] == wp1.joints


def test_replay_empty_trajectory_is_noop(fixtures_dir):
    motion = Motion.from_spec(_spec(fixtures_dir))
    bus = MagicMock()
    estop = MagicMock()
    estop.is_set.return_value = False
    motion.replay([], servo_bus=bus, estop=estop)
    bus.interpolate.assert_not_called()


def test_replay_single_waypoint_interpolates_from_current_position(fixtures_dir):
    """Single-waypoint replay reads current position then interpolates so
    servos actually reach target before the caller drops torque."""
    motion = Motion.from_spec(_spec(fixtures_dir))
    bus = MagicMock()
    bus.read_positions.return_value = {"shoulder_pan": 2048}
    estop = MagicMock()
    estop.is_set.return_value = False

    wp = Waypoint(t=0.0, joints={"shoulder_pan": 2200})
    motion.replay([wp], servo_bus=bus, estop=estop)
    bus.read_positions.assert_called_once()
    bus.interpolate.assert_called_once()
    args = bus.interpolate.call_args.args
    assert args[0] == {"shoulder_pan": 2048}
    assert args[1] == {"shoulder_pan": 2200}


def test_replay_single_waypoint_falls_back_to_write_when_read_empty(fixtures_dir):
    """If read_positions returns nothing, fall back to one-shot write so we
    don't leave the servo uncommanded."""
    motion = Motion.from_spec(_spec(fixtures_dir))
    bus = MagicMock()
    bus.read_positions.return_value = {}
    estop = MagicMock()

    wp = Waypoint(t=0.0, joints={"shoulder_pan": 2200})
    motion.replay([wp], servo_bus=bus, estop=estop)
    bus.write_positions.assert_called_once_with({"shoulder_pan": 2200})
    bus.interpolate.assert_not_called()


def test_replay_respects_hz_from_trajectory(fixtures_dir):
    motion = Motion.from_spec(_spec(fixtures_dir))
    bus = MagicMock()
    estop = MagicMock()
    estop.is_set.return_value = False

    wp0 = Waypoint(t=0.0, joints={"shoulder_pan": 2048})
    wp1 = Waypoint(t=0.5, joints={"shoulder_pan": 2100})

    motion.replay([wp0, wp1], servo_bus=bus, estop=estop, hz=60)
    assert bus.interpolate.call_args.kwargs.get("hz") == 60
