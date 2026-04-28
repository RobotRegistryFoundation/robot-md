from __future__ import annotations

from robot_md.backends.registry import _validate_capability_namespace


def test_core_prefixes_accepted() -> None:
    # Should not raise — these are all core-prefixed.
    _validate_capability_namespace(
        "test_backend",
        frozenset({"arm.pick", "nav.go_to", "perceive.rgb", "gripper.open", "safety.estop"}),
    )
