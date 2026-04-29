# cli/tests/backends/test_existing_capabilities_method_unchanged.py
from __future__ import annotations

from robot_md.backends.feetech_depthai import FeetechDepthaiBackend


def test_capabilities_method_returns_frozenset() -> None:
    b = FeetechDepthaiBackend()
    caps = b.capabilities()
    assert isinstance(caps, frozenset)
    expected = frozenset({
        "arm.pick", "arm.place", "arm.reach", "arm.home",
        "vision.describe", "status.report",
    })
    assert caps == expected


def test_describe_capabilities_default_works_for_feetech() -> None:
    b = FeetechDepthaiBackend()
    out = b.describe_capabilities()
    by_name = {c.name: c for c in out}
    # Core capabilities have arg_schema; vendor (vision., status.) do not.
    assert by_name["arm.pick"].arg_schema is not None
    assert by_name["arm.pick"].namespace == "core"
    assert by_name["vision.describe"].arg_schema is None
    assert by_name["vision.describe"].namespace == "vendor"
