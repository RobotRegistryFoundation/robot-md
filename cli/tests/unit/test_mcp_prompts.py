"""Tests for the 4 MCP prompts: brief-me, check-safety, explain-capability, manifest-status.

Verifies:
- Each prompt is registered (appears in server.list_prompts())
- Each prompt has the expected name and description
- check-safety and explain-capability have the required argument
- Each prompt's handler returns non-empty content
- Prompt text references the robot name where expected
"""

from __future__ import annotations

import pytest

from robot_md.mcp.context import load_context
from robot_md.mcp.server import build_server

# ── fixture ───────────────────────────────────────────────────────────────────


@pytest.fixture
def server_and_name(fixtures_dir):
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    server = build_server(ctx)
    # raw robot name from metadata
    robot_name = ctx.spec.metadata.robot_name
    return server, robot_name


# ── registration tests ────────────────────────────────────────────────────────


async def test_all_four_prompts_registered(server_and_name):
    server, _ = server_and_name
    prompts = await server.list_prompts()
    names = {p.name for p in prompts}
    assert "brief-me" in names, f"brief-me missing from {names}"
    assert "check-safety" in names, f"check-safety missing from {names}"
    assert "explain-capability" in names, f"explain-capability missing from {names}"
    assert "manifest-status" in names, f"manifest-status missing from {names}"


async def test_check_safety_has_action_argument(server_and_name):
    server, _ = server_and_name
    prompts = await server.list_prompts()
    check_safety = next(p for p in prompts if p.name == "check-safety")
    arg_names = [a.name for a in (check_safety.arguments or [])]
    assert "action" in arg_names, f"action arg missing; got {arg_names}"


async def test_explain_capability_has_capability_argument(server_and_name):
    server, _ = server_and_name
    prompts = await server.list_prompts()
    explain = next(p for p in prompts if p.name == "explain-capability")
    arg_names = [a.name for a in (explain.arguments or [])]
    assert "capability" in arg_names, f"capability arg missing; got {arg_names}"


async def test_brief_me_has_no_required_arguments(server_and_name):
    server, _ = server_and_name
    prompts = await server.list_prompts()
    brief_me = next(p for p in prompts if p.name == "brief-me")
    required = [a for a in (brief_me.arguments or []) if a.required]
    assert required == [], f"brief-me should have no required args; got {required}"


async def test_manifest_status_has_no_required_arguments(server_and_name):
    server, _ = server_and_name
    prompts = await server.list_prompts()
    ms = next(p for p in prompts if p.name == "manifest-status")
    required = [a for a in (ms.arguments or []) if a.required]
    assert required == [], f"manifest-status should have no required args; got {required}"


# ── handler content tests ──────────────────────────────────────────────────────


async def test_brief_me_returns_non_empty_content(server_and_name):
    server, _ = server_and_name
    result = await server.get_prompt("brief-me", {})
    assert result.messages, "brief-me returned no messages"
    text = result.messages[0].content.text
    assert len(text) > 50


async def test_brief_me_content_references_robot_name(server_and_name):
    server, robot_name = server_and_name
    result = await server.get_prompt("brief-me", {})
    text = result.messages[0].content.text
    assert robot_name in text, f"Expected robot name '{robot_name}' in brief-me content"


async def test_check_safety_returns_non_empty_content(server_and_name):
    server, _ = server_and_name
    result = await server.get_prompt("check-safety", {"action": "pick up the red cup"})
    assert result.messages, "check-safety returned no messages"
    text = result.messages[0].content.text
    assert len(text) > 50


async def test_check_safety_content_includes_action(server_and_name):
    server, _ = server_and_name
    result = await server.get_prompt("check-safety", {"action": "rotate 180 degrees"})
    text = result.messages[0].content.text
    assert "rotate 180 degrees" in text


async def test_check_safety_content_references_robot_name(server_and_name):
    server, robot_name = server_and_name
    result = await server.get_prompt("check-safety", {"action": "move to shelf"})
    text = result.messages[0].content.text
    assert robot_name in text


async def test_explain_capability_returns_non_empty_content(server_and_name):
    server, _ = server_and_name
    result = await server.get_prompt("explain-capability", {"capability": "arm.pick"})
    assert result.messages, "explain-capability returned no messages"
    text = result.messages[0].content.text
    assert len(text) > 50


async def test_explain_capability_content_includes_capability_name(server_and_name):
    server, _ = server_and_name
    result = await server.get_prompt("explain-capability", {"capability": "arm.pick"})
    text = result.messages[0].content.text
    assert "arm.pick" in text


async def test_manifest_status_returns_non_empty_content(server_and_name):
    server, _ = server_and_name
    result = await server.get_prompt("manifest-status", {})
    assert result.messages, "manifest-status returned no messages"
    text = result.messages[0].content.text
    assert len(text) > 50


async def test_manifest_status_content_references_doctor_summary(server_and_name):
    server, _ = server_and_name
    result = await server.get_prompt("manifest-status", {})
    text = result.messages[0].content.text
    assert "doctor_summary" in text


async def test_manifest_status_content_references_robot_name(server_and_name):
    server, robot_name = server_and_name
    result = await server.get_prompt("manifest-status", {})
    text = result.messages[0].content.text
    assert robot_name in text


# ── description tests ─────────────────────────────────────────────────────────


async def test_prompt_descriptions_are_non_empty(server_and_name):
    server, _ = server_and_name
    prompts = await server.list_prompts()
    for p in prompts:
        if p.name in ("brief-me", "check-safety", "explain-capability", "manifest-status"):
            assert p.description, f"Prompt '{p.name}' has no description"
