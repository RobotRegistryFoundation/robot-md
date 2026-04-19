from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from robot_md.backends.feetech_depthai.capabilities import dispatch
from robot_md.robot_spec import PoseDef


def _backend(*, poses: dict[str, PoseDef] | None = None):
    b = MagicMock()
    b._spec = SimpleNamespace(
        metadata=SimpleNamespace(robot_name="test-bot"),
        physics=SimpleNamespace(poses=dict(poses) if poses else {}),
    )
    b._servo_bus = MagicMock()
    b._servo_bus.read_positions.return_value = {
        "shoulder_pan": 2048,
        "shoulder_lift": 2048,
        "elbow_flex": 2048,
        "wrist_flex": 2048,
        "wrist_roll": 2048,
        "gripper": 1700,
    }
    b._perception = MagicMock()
    b._perception.grab_frame.return_value = (b"rgb", b"depth", None)
    b._motion = MagicMock()
    return b


def _estop():
    e = MagicMock()
    e.is_set.return_value = False
    return e


def test_unknown_capability_returns_error():
    res = dispatch(_backend(), capability="arm.throw", args={}, dry_run=False, estop=_estop())
    assert res.status == "error"
    assert res.error["reason"] == "not_implemented"


def test_arm_pick_invokes_motion_replay():
    b = _backend()
    res = dispatch(b, capability="arm.pick", args={"object": "lego"}, dry_run=False, estop=_estop())
    assert res.status == "ok"
    b._motion.replay.assert_called_once()
    _, kwargs = b._motion.replay.call_args
    assert kwargs["servo_bus"] is b._servo_bus


def test_arm_pick_dry_run_does_not_actuate():
    b = _backend()
    dispatch(b, capability="arm.pick", args={}, dry_run=True, estop=_estop())
    b._motion.replay.assert_not_called()
    b._servo_bus.torque.assert_not_called()


def test_arm_place_invokes_motion_replay():
    b = _backend()
    res = dispatch(b, capability="arm.place", args={}, dry_run=False, estop=_estop())
    assert res.status == "ok"
    b._motion.replay.assert_called_once()


def test_status_report_returns_current_positions():
    b = _backend()
    res = dispatch(b, capability="status.report", args={}, dry_run=False, estop=_estop())
    assert res.status == "ok"
    events = [e for e in res.events if e.kind == "done"]
    assert events
    assert "shoulder_pan" in events[0].data["joints"]


def test_vision_describe_grabs_a_frame():
    b = _backend()
    res = dispatch(b, capability="vision.describe", args={}, dry_run=False, estop=_estop())
    assert res.status == "ok"
    b._perception.grab_frame.assert_called_once()


def test_arm_pick_torque_on_then_off():
    b = _backend()
    dispatch(b, capability="arm.pick", args={}, dry_run=False, estop=_estop())
    torque_calls = [c.args[0] for c in b._servo_bus.torque.call_args_list]
    assert torque_calls == [True, False]


def test_arm_home_uses_poses_ready_when_present():
    """arm.home targets physics.poses.ready, not the hardcoded ZERO."""
    ready = PoseDef(
        joints={
            "shoulder_pan": 1900,
            "shoulder_lift": 1700,
            "elbow_flex": 2048,
            "wrist_flex": 2048,
            "wrist_roll": 2048,
            "gripper": 1700,
        },
        description=None,
        source="taught",
        taught_at=None,
    )
    b = _backend(poses={"ready": ready})
    res = dispatch(b, capability="arm.home", args={}, dry_run=True, estop=_estop())
    assert res.status == "ok"
    final_joints = res.trajectory[-1]["joints"]
    assert final_joints["shoulder_pan"] == 1900
    assert final_joints["shoulder_lift"] == 1700
    assert final_joints["elbow_flex"] == 2048
    assert final_joints["gripper"] == 1700


def test_arm_home_falls_back_to_zero_when_no_ready():
    """No poses.ready -> hardcoded (2048,...,gripper=1700) fallback."""
    b = _backend()  # no poses at all
    res = dispatch(b, capability="arm.home", args={}, dry_run=True, estop=_estop())
    assert res.status == "ok"
    final_joints = res.trajectory[-1]["joints"]
    assert final_joints["shoulder_pan"] == 2048
    assert final_joints["shoulder_lift"] == 2048
    assert final_joints["elbow_flex"] == 2048
    assert final_joints["wrist_flex"] == 2048
    assert final_joints["wrist_roll"] == 2048
    assert final_joints["gripper"] == 1700


def test_arm_home_invokes_motion_replay_when_not_dry_run():
    b = _backend()
    res = dispatch(b, capability="arm.home", args={}, dry_run=False, estop=_estop())
    assert res.status == "ok"
    b._motion.replay.assert_called_once()
    torque_calls = [c.args[0] for c in b._servo_bus.torque.call_args_list]
    assert torque_calls == [True, False]
