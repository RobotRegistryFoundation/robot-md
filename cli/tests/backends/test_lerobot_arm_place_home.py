from __future__ import annotations

from unittest.mock import MagicMock

from robot_md.backends.lerobot import LerobotBackend


def _backend() -> tuple[LerobotBackend, MagicMock]:
    b = LerobotBackend()
    b._robot = MagicMock()
    return b, b._robot


def test_arm_place_dry_run_returns_trajectory() -> None:
    b, robot = _backend()
    result = b.execute("arm.place", {"destination": "drop_zone"}, dry_run=True, estop=None)
    assert result.status == "ok"
    assert result.trajectory is not None
    robot.send_action.assert_not_called()


def test_arm_place_live_invokes_send_action() -> None:
    b, robot = _backend()
    result = b.execute("arm.place", {"destination": "drop_zone"}, dry_run=False, estop=None)
    assert result.status == "ok"
    assert robot.send_action.call_count >= 1


def test_arm_place_missing_destination() -> None:
    b, _ = _backend()
    result = b.execute("arm.place", {}, dry_run=True, estop=None)
    assert result.status == "error"
    assert result.error["reason"] in {"missing_args", "schema_violation"}


def test_arm_home_no_args_succeeds() -> None:
    b, robot = _backend()
    result = b.execute("arm.home", {}, dry_run=False, estop=None)
    assert result.status == "ok"
    robot.send_action.assert_called()


def test_arm_home_dry_run() -> None:
    b, robot = _backend()
    result = b.execute("arm.home", {}, dry_run=True, estop=None)
    assert result.status == "ok"
    assert result.trajectory is not None
    robot.send_action.assert_not_called()
