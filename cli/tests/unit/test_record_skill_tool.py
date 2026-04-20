"""record_skill MCP tool: upsert learned_skills[] entry preserving prose body."""
from __future__ import annotations

from unittest.mock import MagicMock

import yaml

from robot_md.mcp.tools.record_skill import record_skill_tool

_BODY = """
# bob

## Identity
Test fixture.

## What bob Can Do
Testing record_skill upsert.

## Safety Gates
None.
"""


def _base_manifest() -> str:
    return (
        "---\n"
        "rcan_version: '3.0'\n"
        "metadata: {robot_name: bob}\n"
        "physics: {type: arm, dof: 6}\n"
        "drivers: [{id: arm, protocol: feetech}]\n"
        "capabilities: [status.report]\n"
        "safety: {estop: {software: true, response_ms: 100}}\n"
        "---\n" + _BODY
    )


def test_record_skill_appends(tmp_path):
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text(_base_manifest())
    ctx = MagicMock()
    ctx.manifest_path = manifest

    result = record_skill_tool(
        ctx,
        skill_id="red_lego_pick.2026-04-19",
        status="ok",
        validated=["scene_capture", "hsv_red"],
        blocked_by=[],
        notes="Works after poses.ready.",
    )
    assert result["status"] == "ok"
    assert result["count"] == 1
    fm = yaml.safe_load(manifest.read_text().split("---")[1])
    ls = fm["learned_skills"]
    assert ls[0]["id"] == "red_lego_pick.2026-04-19"
    assert ls[0]["status"] == "ok"
    assert ls[0]["validated"] == ["scene_capture", "hsv_red"]
    assert ls[0]["notes"] == "Works after poses.ready."
    assert "recorded_at" in ls[0]


def test_record_skill_upserts_by_id(tmp_path):
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text(
        "---\n"
        "rcan_version: '3.0'\n"
        "metadata: {robot_name: bob}\n"
        "physics: {type: arm, dof: 6}\n"
        "drivers: [{id: arm, protocol: feetech}]\n"
        "capabilities: [status.report]\n"
        "safety: {estop: {software: true, response_ms: 100}}\n"
        "learned_skills:\n"
        "  - {id: x, status: blocked}\n"
        "---\n" + _BODY
    )
    ctx = MagicMock()
    ctx.manifest_path = manifest

    record_skill_tool(ctx, skill_id="x", status="ok", validated=[], blocked_by=[])
    fm = yaml.safe_load(manifest.read_text().split("---")[1])
    ls = fm["learned_skills"]
    assert len(ls) == 1
    assert ls[0]["status"] == "ok"


def test_record_skill_preserves_prose_body(tmp_path):
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text(_base_manifest())
    ctx = MagicMock()
    ctx.manifest_path = manifest

    record_skill_tool(ctx, skill_id="a.b", status="ok", validated=[], blocked_by=[])
    text = manifest.read_text()
    assert "## Identity" in text
    assert "## What bob Can Do" in text
    assert "## Safety Gates" in text


def test_record_skill_omits_notes_when_none(tmp_path):
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text(_base_manifest())
    ctx = MagicMock()
    ctx.manifest_path = manifest

    record_skill_tool(ctx, skill_id="a", status="ok", validated=[], blocked_by=[])
    fm = yaml.safe_load(manifest.read_text().split("---")[1])
    assert "notes" not in fm["learned_skills"][0]
