from __future__ import annotations

from robot_md.backends.realsense import RealsenseBackend


def test_arm_pick_returns_not_implemented() -> None:
    b = RealsenseBackend()
    result = b.execute("arm.pick", {"target": "red_lego"}, dry_run=True, estop=None)
    assert result.status == "error"
    assert result.error["reason"] == "not_implemented"


def test_gripper_open_returns_not_implemented() -> None:
    b = RealsenseBackend()
    result = b.execute("gripper.open", {}, dry_run=True, estop=None)
    assert result.status == "error"
    assert result.error["reason"] == "not_implemented"
