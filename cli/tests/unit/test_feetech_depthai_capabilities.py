from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from robot_md.backends.feetech_depthai.capabilities import dispatch
from robot_md.robot_spec import PoseDef


def _pick_fm() -> dict:
    """Full frontmatter dict used by arm.pick/arm.place — declares the `lego`
    object descriptor, the solver's camera extrinsic, a workspace, and the
    standard 6-DoF kinematic chain."""
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
                "cameras": [
                    {
                        "driver_id": "oakd",
                        "primary_stream": "rgb",
                        "mount": "world",
                        "extrinsic": [0, 0, 0, 0, 0, 0],
                    }
                ],
            },
            "kinematics": [
                {"id": "shoulder_pan", "axis": "z", "a_mm": 0, "d_mm": 60,
                 "zero_pose_steps": 2048, "encoder_sign": 1},
                {"id": "shoulder_lift", "axis": "y", "a_mm": 125, "d_mm": 0,
                 "zero_pose_steps": 2048, "encoder_sign": 1},
                {"id": "elbow_flex", "axis": "y", "a_mm": 125, "d_mm": 0,
                 "zero_pose_steps": 2048, "encoder_sign": 1},
                {"id": "wrist_flex", "axis": "y", "a_mm": 60, "d_mm": 0,
                 "zero_pose_steps": 2048, "encoder_sign": 1},
                {"id": "wrist_roll", "axis": "x", "a_mm": 0, "d_mm": 0,
                 "zero_pose_steps": 2048, "encoder_sign": 1},
                {"id": "gripper", "axis": "y", "a_mm": 0, "d_mm": 0,
                 "zero_pose_steps": 1200, "encoder_sign": 1},
            ],
            "workspace": {"bounds_mm": {"x": [-200, 340], "y": [-340, 340], "z": [0, 250]}},
        },
        "vision": {
            "object_descriptors": [
                {"id": "lego", "detector": "hsv",
                 "params": {"h_ranges": [[0, 10]], "s_min": 110, "v_min": 80, "min_area": 500}}
            ]
        },
    }


def _backend(*, poses: dict[str, PoseDef] | None = None):
    b = MagicMock()
    b._spec = SimpleNamespace(
        metadata=SimpleNamespace(robot_name="test-bot"),
        physics=SimpleNamespace(poses=dict(poses) if poses else {}),
    )
    b.raw_frontmatter = _pick_fm()
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
    b._perception.vision_find.return_value = {
        "status": "ok",
        "descriptor": "lego",
        "xyz_cam_mm": (100.0, 0.0, 50.0),
    }
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
    res = dispatch(
        b, capability="arm.pick", args={"target": "lego"}, dry_run=False, estop=_estop()
    )
    assert res.status == "ok", res.error
    b._motion.replay.assert_called_once()
    _, kwargs = b._motion.replay.call_args
    assert kwargs["servo_bus"] is b._servo_bus


def test_arm_pick_dry_run_does_not_actuate():
    b = _backend()
    dispatch(b, capability="arm.pick", args={"target": "lego"}, dry_run=True, estop=_estop())
    b._motion.replay.assert_not_called()
    b._servo_bus.torque.assert_not_called()


def test_arm_place_invokes_motion_replay():
    b = _backend()
    res = dispatch(
        b, capability="arm.place", args={"target": "lego"}, dry_run=False, estop=_estop()
    )
    assert res.status == "ok", res.error
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
    dispatch(b, capability="arm.pick", args={"target": "lego"}, dry_run=False, estop=_estop())
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
