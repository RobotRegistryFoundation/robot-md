from __future__ import annotations

from unittest.mock import MagicMock

from robot_md.backends.lerobot import LerobotBackend


def test_unknown_capability_returns_not_implemented() -> None:
    b = LerobotBackend()
    b._robot = MagicMock()
    result = b.execute("arm.dance", {}, dry_run=True, estop=None)
    assert result.status == "error"
    assert result.error["reason"] == "not_implemented"


def test_misspelled_core_capability_also_returns_not_implemented() -> None:
    b = LerobotBackend()
    b._robot = MagicMock()
    result = b.execute("gripper.opn", {}, dry_run=True, estop=None)
    assert result.status == "error"
    assert result.error["reason"] == "not_implemented"
