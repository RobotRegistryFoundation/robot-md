"""estop_clear is refused inside robot-md's MCP server, and sends nothing.

Clearing a stop makes the robot movable again, so it is the person's act,
with their own commission-tier credential. The MCP server never holds that
credential and never asks the gateway to clear: `estop_clear` refuses and
says how the person clears the stop. This server's own latch is released
only when the server restarts (`/mcp` -> robot-md -> Reconnect): neither
so-arm101-actuator nor robot-md-gateway reports the actuator's latch in any
read, so the server cannot tell reliably that the person cleared it.

It used to clear an in-process flag on any non-empty `confirm_token`, and
then (in the first version of this change) to ask the gateway at the
commission tier.
"""

from __future__ import annotations

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from robot_md import gateway_client
from robot_md.mcp.context import load_context
from robot_md.mcp.server import build_server
from robot_md.mcp.tools.estop import estop_clear_tool, estop_tool
from robot_md.robot_spec import RobotSpec

MANIFEST = "robot_md_oak_d_factory_cal.yaml"


def _assert_refused_with_instructions(r: dict) -> None:
    assert r["ok"] is False
    assert r["stop"] == "not_cleared"
    assert r["error"]["reason"] == "person_clears_stops"
    text = r["message"]
    for needle in ("commission", "arm.estop.clear", "/v1/safety/clear", "Reconnect"):
        assert needle in text, f"the instructions don't mention {needle!r}"


def test_estop_clear_sends_nothing_and_keeps_the_latch(fixtures_dir, gateway_env):
    ctx = load_context(fixtures_dir / MANIFEST)
    estop_tool(ctx)
    sent = len(gateway_env.requests)
    r = estop_clear_tool(ctx)
    _assert_refused_with_instructions(r)
    assert len(gateway_env.requests) == sent, "estop_clear contacted the gateway"
    assert ctx.estop.is_set()


def test_the_instructions_give_a_clear_the_gateway_accepts(fixtures_dir, gateway_env, monkeypatch):
    """The person's clear names the ROBOT.md the gateway pins (with their own
    copy's path the gateway answers `manifest_pin`) and the COMMISSION scope
    (under `actuate`, install-gateway's HiTL setting and a `system` gate refuse
    it). They also say the gateway's own clear must be signed where signatures
    are required, and which command builds it."""
    monkeypatch.setenv(gateway_client.ENV_MANIFEST_PATH, "/etc/robot-md-gateway/ROBOT.md")
    ctx = load_context(fixtures_dir / MANIFEST)
    text = estop_clear_tool(ctx)["message"]
    assert (
        "robot-md invoke /etc/robot-md-gateway/ROBOT.md --tool arm.estop.clear "
        "--scope COMMISSION" in text
    )
    assert "ESTOP_CLEAR" in text
    assert "robot-md-gateway#36" in text
    assert "robot-md-gateway#35 or later" in text


def test_estop_clear_refuses_whatever_credential_the_server_holds(
    fixtures_dir, gateway_env, monkeypatch
):
    """Even a server someone gave a commission bearer sends no clear."""
    monkeypatch.setenv(gateway_client.ENV_BEARER, "a-commission-bearer-for-this-test")
    ctx = load_context(fixtures_dir / MANIFEST)
    ctx.estop.set()
    r = estop_clear_tool(ctx)
    _assert_refused_with_instructions(r)
    assert gateway_env.requests == []
    assert ctx.estop.is_set()


def test_estop_clear_without_a_gateway_refuses_the_same_way(fixtures_dir):
    ctx = load_context(fixtures_dir / MANIFEST)
    ctx.estop.set()
    _assert_refused_with_instructions(estop_clear_tool(ctx))
    assert ctx.estop.is_set()


def test_a_declared_gate_changes_nothing(fixtures_dir, gateway_env):
    ctx = load_context(fixtures_dir / MANIFEST)
    ctx.parsed.frontmatter["safety"].setdefault("hitl_gates", []).append(
        {"scope": "system", "require_auth": True}
    )
    ctx.spec = RobotSpec.from_parsed(ctx.parsed)
    ctx.estop.set()
    _assert_refused_with_instructions(estop_clear_tool(ctx))
    assert gateway_env.requests == []


async def test_estop_clear_through_mcp_is_an_error_with_the_instructions(fixtures_dir, gateway_env):
    ctx = load_context(fixtures_dir / MANIFEST)
    ctx.estop.set()
    server = build_server(ctx)
    with pytest.raises(ToolError, match="commission"):
        await server.call_tool("estop_clear", {})
    assert ctx.estop.is_set()
    assert gateway_env.requests == []


def test_a_restart_is_what_releases_the_latch(fixtures_dir, gateway_env):
    """The latch lives in the server process; a new context starts clear."""
    ctx = load_context(fixtures_dir / MANIFEST)
    estop_tool(ctx)
    assert ctx.estop.is_set()
    assert not load_context(fixtures_dir / MANIFEST).estop.is_set()
