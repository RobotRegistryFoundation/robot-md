"""Test LerobotBackend protocols and read-only capabilities."""

from __future__ import annotations

from robot_md.backends.lerobot import LerobotBackend


def test_name_and_protocols() -> None:
    b = LerobotBackend()
    assert b.name == "lerobot"
    assert b.protocols == frozenset({"feetech", "dynamixel"})


def test_read_only_capabilities_marks_perception() -> None:
    b = LerobotBackend()
    assert b.read_only_capabilities == frozenset({"perceive.rgb", "perceive.depth"})
