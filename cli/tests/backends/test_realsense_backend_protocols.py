"""Test RealsenseBackend class attributes and basic protocol info."""

from __future__ import annotations

from robot_md.backends.realsense import RealsenseBackend


def test_name_and_protocols() -> None:
    b = RealsenseBackend()
    assert b.name == "realsense"
    assert b.protocols == frozenset({"realsense"})


def test_read_only_capabilities_marks_perception() -> None:
    b = RealsenseBackend()
    assert b.read_only_capabilities == frozenset({"perceive.rgb", "perceive.depth"})
