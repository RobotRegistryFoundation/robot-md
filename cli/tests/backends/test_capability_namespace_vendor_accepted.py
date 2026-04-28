from __future__ import annotations

from robot_md.backends.registry import _validate_capability_namespace


def test_vendor_namespaced_accepted() -> None:
    _validate_capability_namespace(
        "test_backend",
        frozenset({
            "lerobot.teleop",
            "realsense.aligned_depth",
            "franka.cartesian_impedance",
            "my_corp.skill_x",
        }),
    )
