# cli/tests/backends/test_capability_dataclass.py
from __future__ import annotations

import pytest

from robot_md.backends.capability import Capability, derive_namespace


def test_capability_is_frozen_dataclass() -> None:
    cap = Capability(name="arm.pick", namespace="core", arg_schema=None, description="")
    with pytest.raises(Exception):
        cap.name = "arm.place"  # frozen — must raise


def test_derive_namespace_core_prefixes() -> None:
    for name in ("arm.pick", "nav.go_to", "perceive.rgb", "gripper.open", "safety.estop"):
        assert derive_namespace(name) == "core"


def test_derive_namespace_vendor() -> None:
    for name in ("lerobot.teleop", "realsense.aligned_depth", "my_corp.skill_x"):
        assert derive_namespace(name) == "vendor"


def test_derive_namespace_vendor_for_existing_feetech_capabilities() -> None:
    # vision.describe and status.report are NOT in CORE_CAPABILITY_PREFIXES;
    # they are vendor-shaped and should be classified as vendor.
    assert derive_namespace("vision.describe") == "vendor"
    assert derive_namespace("status.report") == "vendor"
