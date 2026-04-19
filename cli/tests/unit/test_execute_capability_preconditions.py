"""execute_capability returns status=blocked when a precondition fails."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from robot_md.mcp.context import load_context
from robot_md.mcp.tools.execute_capability import execute_capability_tool

_BODY = (
    "# bob\n\n"
    "## Identity\nBob is a test arm.\n\n"
    "## What bob Can Do\nPick things.\n\n"
    "## Safety Gates\nSoftware E-stop at 100ms.\n"
)


def _manifest_with_contract(tmp_path: Path) -> Path:
    p = tmp_path / "ROBOT.md"
    p.write_text(
        "---\n"
        "rcan_version: '3.0'\n"
        "metadata: {robot_name: bob}\n"
        "physics: {type: arm, dof: 6}\n"
        "drivers: [{id: arm, protocol: feetech, port: /dev/null}]\n"
        "capabilities: [arm.pick, status.report]\n"
        "capability_contracts:\n"
        "  arm.pick:\n"
        "    preconditions: [{kind: pose_taught, name: ready}]\n"
        "safety:\n"
        "  estop: {software: true, response_ms: 100}\n"
        "  max_joint_velocity_dps: 180\n"
        "---\n" + _BODY
    )
    return p


def _manifest_without_contract(tmp_path: Path) -> Path:
    p = tmp_path / "ROBOT.md"
    p.write_text(
        "---\n"
        "rcan_version: '3.0'\n"
        "metadata: {robot_name: bob}\n"
        "physics: {type: arm, dof: 6}\n"
        "drivers: [{id: arm, protocol: feetech, port: /dev/null}]\n"
        "capabilities: [arm.pick, status.report]\n"
        "safety:\n"
        "  estop: {software: true, response_ms: 100}\n"
        "  max_joint_velocity_dps: 180\n"
        "---\n" + _BODY
    )
    return p


def test_execute_capability_blocks_when_pose_missing(tmp_path):
    """Contract declares pose_taught but manifest has no poses.ready → blocked."""
    ctx = load_context(_manifest_with_contract(tmp_path))
    # Stub backend so the capability/backend-implemented checks pass.
    ctx.backend = MagicMock()
    ctx.backend.capabilities.return_value = frozenset({"arm.pick"})

    result = execute_capability_tool(
        ctx, capability="arm.pick", args={}, dry_run=True, confirm_token=None
    )
    assert result["status"] == "blocked"
    assert result["error"]["reason"] == "precondition"
    assert any("pose 'ready' not taught" in f for f in result["error"]["failed"])


def test_execute_capability_passes_when_contract_absent(tmp_path):
    """No capability_contracts block → existing behaviour unchanged (no gate)."""
    from robot_md.backends.base import ExecutionResult

    ctx = load_context(_manifest_without_contract(tmp_path))
    ctx.backend = MagicMock()
    ctx.backend.capabilities.return_value = frozenset({"arm.pick"})
    ctx.backend.read_only_capabilities = frozenset()
    ctx.backend.execute.return_value = ExecutionResult(
        status="ok", trajectory=[], events=[], error=None,
    )
    # Safety.hitl_gates will match nothing for "arm.pick" unless declared.
    result = execute_capability_tool(
        ctx, capability="arm.pick", args={}, dry_run=True, confirm_token=None
    )
    assert result["status"] == "ok", result
