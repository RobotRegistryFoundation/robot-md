"""Test LerobotBackend capability set and namespace validation."""

from __future__ import annotations

from robot_md.backends.lerobot import LerobotBackend
from robot_md.backends.registry import _validate_capability_namespace


def test_all_declared_capabilities_pass_tier_validator() -> None:
    b = LerobotBackend()
    _validate_capability_namespace("lerobot", b.capabilities())


def test_capabilities_set_contents() -> None:
    b = LerobotBackend()
    assert b.capabilities() == frozenset(
        {
            "arm.pick",
            "arm.place",
            "arm.home",
            "perceive.rgb",
            "perceive.depth",
            "gripper.open",
            "gripper.close",
            "lerobot.teleop",
        }
    )
