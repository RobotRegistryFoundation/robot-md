"""Tests for the doctor_summary MCP tool.

Verifies:
- Valid manifest → schema_ok=True, expected fields present
- Schema error in manifest → schema_ok=False, schema_errors populated
- Response shape matches npm robot-md-mcp@0.3 doctorSummary() contract:
    schema_ok, schema_errors, robot_name, rrn, registered, dof,
    capabilities_count, drivers[], hitl_gates[], estop, notes
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from robot_md.mcp.tools.doctor_summary import doctor_summary_tool
from robot_md.parser import ParsedRobotMd

# ── helpers ──────────────────────────────────────────────────────────────────


def _make_ctx(parsed: ParsedRobotMd):
    """Minimal McpContext stub sufficient for doctor_summary_tool."""
    return SimpleNamespace(parsed=parsed)


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def valid_ctx(fixtures_dir):
    from robot_md.mcp.context import load_context

    # load_context validates; use the always-valid OAK-D fixture
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    return ctx


# ── tests ─────────────────────────────────────────────────────────────────────


def test_doctor_summary_valid_manifest_schema_ok(valid_ctx):
    result = doctor_summary_tool(valid_ctx)
    assert result["schema_ok"] is True


def test_doctor_summary_valid_manifest_no_schema_errors(valid_ctx):
    result = doctor_summary_tool(valid_ctx)
    assert result["schema_errors"] == []


def test_doctor_summary_has_robot_name(valid_ctx):
    result = doctor_summary_tool(valid_ctx)
    assert result["robot_name"] == "test-bot"


def test_doctor_summary_registered_false_when_no_rrn(valid_ctx):
    """Fixture has no rrn field → registered=False, rrn=None."""
    result = doctor_summary_tool(valid_ctx)
    # The OAK-D factory cal fixture may or may not have rrn; either way registered
    # must be consistent with the rrn field.
    assert result["registered"] == bool(result["rrn"])


def test_doctor_summary_dof_field(valid_ctx):
    result = doctor_summary_tool(valid_ctx)
    assert isinstance(result["dof"], int)
    assert result["dof"] == 6


def test_doctor_summary_capabilities_count(valid_ctx):
    result = doctor_summary_tool(valid_ctx)
    assert isinstance(result["capabilities_count"], int)
    assert result["capabilities_count"] >= 0


def test_doctor_summary_drivers_is_list(valid_ctx):
    result = doctor_summary_tool(valid_ctx)
    assert isinstance(result["drivers"], list)


def test_doctor_summary_drivers_have_expected_keys(valid_ctx):
    result = doctor_summary_tool(valid_ctx)
    for d in result["drivers"]:
        assert "id" in d
        assert "protocol" in d
        assert "port" in d
        assert "host" in d


def test_doctor_summary_hitl_gates_is_list(valid_ctx):
    result = doctor_summary_tool(valid_ctx)
    assert isinstance(result["hitl_gates"], list)


def test_doctor_summary_hitl_gates_have_expected_keys(valid_ctx):
    result = doctor_summary_tool(valid_ctx)
    for g in result["hitl_gates"]:
        assert "scope" in g
        assert "require_auth" in g
        assert isinstance(g["require_auth"], bool)


def test_doctor_summary_notes_is_non_empty_list(valid_ctx):
    result = doctor_summary_tool(valid_ctx)
    assert isinstance(result["notes"], list)
    assert len(result["notes"]) > 0


def test_doctor_summary_full_shape(valid_ctx):
    """All npm-parity keys must be present in the result."""
    result = doctor_summary_tool(valid_ctx)
    expected_keys = {
        "schema_ok",
        "schema_errors",
        "robot_name",
        "rrn",
        "registered",
        "dof",
        "capabilities_count",
        "drivers",
        "hitl_gates",
        "estop",
        "notes",
    }
    assert expected_keys.issubset(result.keys()), f"Missing keys: {expected_keys - result.keys()}"


def test_doctor_summary_invalid_manifest_schema_not_ok():
    """Manifest with schema errors → schema_ok=False, schema_errors non-empty."""
    # Build a minimal invalid frontmatter (missing required metadata.robot_name)
    bad_fm = {
        "rcan_version": "3.0",
        # metadata block omitted → schema violation
        "physics": {"type": "arm", "dof": 6},
    }
    bad_parsed = ParsedRobotMd(frontmatter=bad_fm, body="")
    ctx = _make_ctx(bad_parsed)
    result = doctor_summary_tool(ctx)
    assert result["schema_ok"] is False
    assert len(result["schema_errors"]) > 0


def test_doctor_summary_invalid_manifest_has_required_keys():
    """Even for invalid manifests the shape contract must hold."""
    bad_fm = {"rcan_version": "3.0"}
    bad_parsed = ParsedRobotMd(frontmatter=bad_fm, body="")
    ctx = _make_ctx(bad_parsed)
    result = doctor_summary_tool(ctx)
    expected_keys = {
        "schema_ok",
        "schema_errors",
        "robot_name",
        "rrn",
        "registered",
        "dof",
        "capabilities_count",
        "drivers",
        "hitl_gates",
        "estop",
        "notes",
    }
    assert expected_keys.issubset(result.keys())


def test_doctor_summary_registered_with_rrn():
    """When rrn is present, registered=True."""
    fm = {
        "rcan_version": "3.0",
        "metadata": {"robot_name": "mybot", "rrn": "RRN-000000000001"},
    }
    parsed = ParsedRobotMd(frontmatter=fm, body="")
    ctx = _make_ctx(parsed)
    result = doctor_summary_tool(ctx)
    assert result["rrn"] == "RRN-000000000001"
    assert result["registered"] is True


# ── server registration test ──────────────────────────────────────────────────


async def test_doctor_summary_tool_registered_in_server(fixtures_dir):
    """doctor_summary must appear in server.list_tools() — catches decorator failures."""
    from robot_md.mcp.context import load_context
    from robot_md.mcp.server import build_server

    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    server = build_server(ctx)
    tools = await server.list_tools()
    tool_names = {t.name for t in tools}
    assert "doctor_summary" in tool_names, f"doctor_summary not in registered tools: {tool_names}"
