"""Test RealsenseBackend capability set (perception only, no motion)."""

from __future__ import annotations

from robot_md.backends.realsense import RealsenseBackend


def test_capabilities_are_perception_plus_aligned_depth() -> None:
    b = RealsenseBackend()
    caps = b.capabilities()
    assert caps == frozenset(
        {
            "perceive.rgb",
            "perceive.depth",
            "realsense.aligned_depth",
        }
    )


def test_no_arm_or_gripper_capabilities() -> None:
    b = RealsenseBackend()
    caps = b.capabilities()
    for cap in caps:
        assert not cap.startswith("arm."), f"unexpected arm capability {cap}"
        assert not cap.startswith("gripper."), f"unexpected gripper capability {cap}"
