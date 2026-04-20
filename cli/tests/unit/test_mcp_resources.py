"""Pure-function MCP resource builders. Tests do not start FastMCP."""
from __future__ import annotations

from unittest.mock import MagicMock

from robot_md.mcp.resources import calibration_status, learned_skills, poses
from robot_md.robot_spec import LearnedSkill, PoseDef


def _ctx(*, poses_dict=None, cameras=(), solver=None, ls=()):
    spec = MagicMock()
    spec.physics.poses = poses_dict or {}
    spec.physics.cameras = cameras
    spec.physics.solver = solver or {}
    spec.learned_skills = ls
    ctx = MagicMock()
    ctx.spec = spec
    return ctx


def test_calibration_status_all_missing():
    r = calibration_status(_ctx())
    assert r["zero"] == "ok"  # zero_pose_steps is always present in shipped presets
    assert r["hand_eye"] == "missing"
    assert r["poses_ready"] == "missing"


def test_calibration_status_ready_taught():
    r = calibration_status(_ctx(
        poses_dict={"ready": PoseDef(
            joints={"a": 1}, description=None, source="taught", taught_at=None,
        )}
    ))
    assert r["poses_ready"] == "ok"


def test_calibration_status_hand_eye_present():
    cam = MagicMock()
    cam.extrinsic = (1, 0, 0, 0)
    r = calibration_status(_ctx(cameras=(cam,)))
    assert r["hand_eye"] == "ok"


def test_learned_skills_returns_list_of_dicts():
    r = learned_skills(_ctx(ls=(
        LearnedSkill(
            id="x", status="ok",
            validated=("a","b"), blocked_by=(), notes=None, recorded_at=None,
        ),
    )))
    assert isinstance(r, list)
    assert r[0]["id"] == "x"
    assert r[0]["validated"] == ["a", "b"]


def test_learned_skills_empty_list_when_none():
    r = learned_skills(_ctx())
    assert r == []


def test_poses_resource_returns_dict():
    r = poses(_ctx(poses_dict={
        "ready": PoseDef(
            joints={"a": 1}, description="x",
            source="taught", taught_at="2026-04-19",
        )
    }))
    assert r["ready"]["joints"] == {"a": 1}
    assert r["ready"]["source"] == "taught"
    assert r["ready"]["taught_at"] == "2026-04-19"


def test_poses_resource_empty_dict_when_none():
    r = poses(_ctx())
    assert r == {}


def test_calibration_status_zero_missing_when_joints_lack_zero_pose_steps():
    """If any kinematic joint is missing zero_pose_steps, zero reports 'missing'."""
    spec = MagicMock()
    spec.physics.poses = {}
    spec.physics.cameras = ()
    spec.physics.solver = {}
    # Two joints declared: one with zero_pose_steps, one without.
    spec.physics.kinematics = (
        {"id": "shoulder_pan", "zero_pose_steps": 2048},
        {"id": "elbow_flex"},  # missing zero_pose_steps
    )
    spec.learned_skills = ()
    ctx = MagicMock()
    ctx.spec = spec
    r = calibration_status(ctx)
    assert r["zero"] == "missing"


def test_calibration_status_zero_ok_when_all_joints_have_zero_pose_steps():
    spec = MagicMock()
    spec.physics.poses = {}
    spec.physics.cameras = ()
    spec.physics.solver = {}
    spec.physics.kinematics = (
        {"id": "a", "zero_pose_steps": 2048},
        {"id": "b", "zero_pose_steps": 2100},
    )
    spec.learned_skills = ()
    ctx = MagicMock()
    ctx.spec = spec
    r = calibration_status(ctx)
    assert r["zero"] == "ok"


def test_calibration_status_zero_missing_when_no_kinematics():
    """Zero-DoF sensors / non-kinematic robots: no joints to calibrate -> 'missing'."""
    spec = MagicMock()
    spec.physics.poses = {}
    spec.physics.cameras = ()
    spec.physics.solver = {}
    spec.physics.kinematics = ()
    spec.learned_skills = ()
    ctx = MagicMock()
    ctx.spec = spec
    r = calibration_status(ctx)
    # No kinematics declared — zero cal not meaningful. Report missing.
    assert r["zero"] == "missing"


def test_resources_handle_none_spec():
    """Builder with ctx.spec=None returns safe empty payloads, does not raise."""
    ctx = MagicMock()
    ctx.spec = None
    expected = {"zero": "missing", "hand_eye": "missing", "poses_ready": "missing"}
    assert calibration_status(ctx) == expected
    assert learned_skills(ctx) == []
    assert poses(ctx) == {}


def test_sanitize_robot_name_for_uri():
    from robot_md.mcp.resources import _sanitize_robot_name
    assert _sanitize_robot_name("bob") == "bob"
    assert _sanitize_robot_name("bob-mk2") == "bob-mk2"
    assert _sanitize_robot_name("bob_01") == "bob_01"
    assert _sanitize_robot_name("bob cat") == "bob-cat"
    assert _sanitize_robot_name("a/b") == "a-b"
    assert _sanitize_robot_name("") == "robot"
    assert _sanitize_robot_name(None) == "robot"
    assert _sanitize_robot_name("!!!") == "robot"
