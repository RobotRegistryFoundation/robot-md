from __future__ import annotations

from unittest.mock import MagicMock

from robot_md.backends.lerobot import LerobotBackend


def test_dry_run_arm_pick_populates_trajectory_and_skips_writes() -> None:
    b = LerobotBackend()
    robot = MagicMock()
    b._robot = robot
    result = b.execute("arm.pick", {"target": "red_lego"}, dry_run=True, estop=None)
    assert result.status == "ok"
    assert isinstance(result.trajectory, list)
    assert len(result.trajectory) >= 2  # at least approach + descend
    robot.send_action.assert_not_called()


def test_dry_run_arm_place_populates_trajectory() -> None:
    b = LerobotBackend()
    robot = MagicMock()
    b._robot = robot
    result = b.execute("arm.place", {"destination": "drop_zone"}, dry_run=True, estop=None)
    assert result.status == "ok"
    assert isinstance(result.trajectory, list)
    robot.send_action.assert_not_called()


def test_dry_run_arm_home_populates_trajectory() -> None:
    b = LerobotBackend()
    robot = MagicMock()
    b._robot = robot
    result = b.execute("arm.home", {}, dry_run=True, estop=None)
    assert result.status == "ok"
    assert isinstance(result.trajectory, list)
    robot.send_action.assert_not_called()
