from __future__ import annotations

from unittest.mock import MagicMock

from robot_md.backends.lerobot import LerobotBackend


def test_teleop_loop_streams_leader_to_follower() -> None:
    b = LerobotBackend()
    robot = MagicMock()
    leader_states = [
        {"joints": [0.1, 0.0, 0.0, 0.0, 0.0, 0.0]},
        {"joints": [0.2, 0.0, 0.0, 0.0, 0.0, 0.0]},
        None,  # sentinel — leader disconnected
    ]
    robot.read_leader_state.side_effect = leader_states
    b._robot = robot
    result = b.execute("lerobot.teleop", {"max_steps": 10}, dry_run=False, estop=None)
    assert result.status == "ok"
    assert robot.send_action.call_count == 2  # stops at None sentinel before max_steps


def test_teleop_respects_max_steps() -> None:
    b = LerobotBackend()
    robot = MagicMock()
    # Always returns a state — never the None sentinel.
    robot.read_leader_state.return_value = {"joints": [0.1, 0.0, 0.0, 0.0, 0.0, 0.0]}
    b._robot = robot
    result = b.execute("lerobot.teleop", {"max_steps": 3}, dry_run=False, estop=None)
    assert result.status == "ok"
    assert robot.send_action.call_count == 3


def test_teleop_dry_run_does_not_call_robot() -> None:
    b = LerobotBackend()
    b._robot = MagicMock()
    result = b.execute("lerobot.teleop", {"max_steps": 5}, dry_run=True, estop=None)
    assert result.status == "ok"
    b._robot.send_action.assert_not_called()
    b._robot.read_leader_state.assert_not_called()


def test_teleop_default_max_steps_when_arg_missing() -> None:
    b = LerobotBackend()
    b._robot = MagicMock()
    # Default should still be safe (finite); just verify a dry_run completes.
    result = b.execute("lerobot.teleop", {}, dry_run=True, estop=None)
    assert result.status == "ok"
