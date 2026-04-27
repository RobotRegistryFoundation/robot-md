"""Verify the 9 SP6 spatial_eval_* tools are registered on the MCP server (T30)."""

from __future__ import annotations

import pytest

from robot_md.mcp.context import load_context
from robot_md.mcp.server import build_server


@pytest.fixture
def server(fixtures_dir):
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    return build_server(ctx)


async def test_all_nine_spatial_eval_tools_registered(server):
    tools = await server.list_tools()
    names = {t.name for t in tools}
    expected = {
        "spatial_eval_dry_run",
        "spatial_eval_init",
        "spatial_eval_kit",
        "spatial_eval_run_probe",
        "spatial_eval_run_execute",
        "spatial_eval_run_full",
        "spatial_eval_replay",
        "spatial_eval_verify",
        "spatial_eval_submit_to_rrf",
    }
    missing = expected - names
    assert not missing, f"missing tools: {missing}"


async def test_spatial_eval_tools_exclude_private_injection_kwargs(server):
    """Public MCP surface must not expose `_stacks`, `_robot`, `_judge_camera`,
    `_verify_signature` — those are test-only injection kwargs on the underlying
    tool functions, not part of the published JSON schema."""
    tools = await server.list_tools()
    for t in tools:
        if not t.name.startswith("spatial_eval_"):
            continue
        params = (t.inputSchema or {}).get("properties", {})
        leaked = [p for p in params if p.startswith("_")]
        assert not leaked, f"{t.name} leaks private kwargs: {leaked}"
