from __future__ import annotations

from unittest.mock import MagicMock

from robot_md.backends.lerobot import LerobotBackend


def _backend() -> tuple[LerobotBackend, MagicMock]:
    b = LerobotBackend()
    b._robot = MagicMock()
    return b, b._robot


def test_gripper_open_sends_open_command() -> None:
    b, robot = _backend()
    result = b.execute("gripper.open", {}, dry_run=False, estop=None)
    assert result.status == "ok"
    robot.send_action.assert_called_once()
    sent = robot.send_action.call_args.args[0]
    assert sent.get("gripper") == "open"


def test_gripper_open_dry_run_skips_writes() -> None:
    b, robot = _backend()
    result = b.execute("gripper.open", {}, dry_run=True, estop=None)
    assert result.status == "ok"
    assert result.trajectory is not None
    robot.send_action.assert_not_called()


def test_gripper_close_sends_close_command() -> None:
    b, robot = _backend()
    result = b.execute("gripper.close", {}, dry_run=False, estop=None)
    assert result.status == "ok"
    sent = robot.send_action.call_args.args[0]
    assert sent.get("gripper") == "close"


def test_gripper_close_dry_run_skips_writes() -> None:
    b, robot = _backend()
    result = b.execute("gripper.close", {}, dry_run=True, estop=None)
    assert result.status == "ok"
    assert result.trajectory is not None
    robot.send_action.assert_not_called()
