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
