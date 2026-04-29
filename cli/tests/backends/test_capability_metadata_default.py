# cli/tests/backends/test_capability_metadata_default.py
from __future__ import annotations

from robot_md.backends._capability_default import describe_default


def test_default_returns_capability_objects() -> None:
    out = describe_default("test_backend", frozenset({"arm.pick"}))
    assert len(out) == 1
    cap = out[0]
    assert cap.name == "arm.pick"
    assert cap.namespace == "core"
    assert cap.arg_schema is not None
    assert cap.arg_schema.get("required") == ["target"]


def test_default_for_core_capability_with_no_schema_entry() -> None:
    # No core capability is currently absent from capabilities.json,
    # but the default must handle the drift case gracefully.
    out = describe_default("test_backend", frozenset({"arm.future_capability"}))
    assert len(out) == 1
    cap = out[0]
    assert cap.name == "arm.future_capability"
    assert cap.namespace == "core"
    assert cap.arg_schema is None
    assert cap.description == ""


def test_default_for_vendor_capability() -> None:
    out = describe_default("lerobot", frozenset({"lerobot.teleop"}))
    assert len(out) == 1
    cap = out[0]
    assert cap.name == "lerobot.teleop"
    assert cap.namespace == "vendor"
    assert cap.arg_schema is None
    assert cap.description == ""


def test_default_for_existing_feetech_capabilities() -> None:
    # vision.describe and status.report from feetech_depthai → vendor with None schema.
    out = describe_default(
        "feetech_depthai",
        frozenset({"vision.describe", "status.report"}),
    )
    by_name = {c.name: c for c in out}
    assert by_name["vision.describe"].namespace == "vendor"
    assert by_name["vision.describe"].arg_schema is None
    assert by_name["status.report"].namespace == "vendor"
    assert by_name["status.report"].arg_schema is None
