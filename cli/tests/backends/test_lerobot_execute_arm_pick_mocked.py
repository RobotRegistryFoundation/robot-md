from __future__ import annotations

from unittest.mock import MagicMock

from robot_md.backends.lerobot import LerobotBackend


def _backend_with_robot() -> tuple[LerobotBackend, MagicMock]:
    b = LerobotBackend()
    robot = MagicMock(name="lerobot_robot")
    b._robot = robot
    return b, robot


def test_arm_pick_dry_run_emits_trajectory_no_writes() -> None:
    b, robot = _backend_with_robot()
    result = b.execute("arm.pick", {"target": "red_lego"}, dry_run=True, estop=None)
    assert result.status == "ok"
    assert result.trajectory is not None
    assert len(result.trajectory) >= 2
    robot.send_action.assert_not_called()


def test_arm_pick_live_invokes_send_action() -> None:
    b, robot = _backend_with_robot()
    result = b.execute("arm.pick", {"target": "red_lego"}, dry_run=False, estop=None)
    assert result.status == "ok"
    robot.send_action.assert_called()
    # Loose-OR assertion: first call should mention "approach" via str() OR carry a "joints" key.
    # (Reviewer note: intentionally loose so the test doesn't pin the exact phase keyword.)
    first_call_args = robot.send_action.call_args_list[0].args[0]
    assert "approach" in str(first_call_args).lower() or "joints" in first_call_args


def test_arm_pick_missing_target_returns_error() -> None:
    b, _ = _backend_with_robot()
    result = b.execute("arm.pick", {}, dry_run=True, estop=None)
    assert result.status == "error"
    assert result.error["reason"] in {"missing_args", "schema_violation"}


def test_arm_pick_non_string_target_returns_schema_violation() -> None:
    b, _ = _backend_with_robot()
    result = b.execute("arm.pick", {"target": 42}, dry_run=True, estop=None)
    assert result.status == "error"
    assert result.error["reason"] == "schema_violation"
