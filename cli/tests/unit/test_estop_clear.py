"""estop_clear asks robot-md-gateway, at the commission tier, and nothing else.

It used to clear an in-process flag, gated by a `system` HITL scope that any
non-empty `confirm_token` satisfied. Clearing a stop makes the robot movable
again; it is now the gateway's decision, made against a commission-tier
credential, and this server's latch follows the gateway's answer.
"""

from __future__ import annotations

from robot_md.mcp.context import load_context
from robot_md.mcp.tools.estop import estop_clear_tool, estop_tool
from robot_md.robot_spec import RobotSpec

MANIFEST = "robot_md_oak_d_factory_cal.yaml"


def test_estop_clear_releases_the_latch_only_when_the_gateway_clears(fixtures_dir, gateway_env):
    ctx = load_context(fixtures_dir / MANIFEST)
    estop_tool(ctx)
    assert ctx.estop.is_set()
    r = estop_clear_tool(ctx)
    assert r["ok"] is True
    assert not ctx.estop.is_set()
    assert r["cleared_at"] > 0
    assert gateway_env.bodies[-1]["tool_name"] == "arm.estop.clear"
    assert gateway_env.bodies[-1]["scope"] == "COMMISSION"


def test_estop_clear_refused_by_the_gateway_keeps_the_latch(fixtures_dir, gateway_env):
    ctx = load_context(fixtures_dir / MANIFEST)
    estop_tool(ctx)
    gateway_env.deny(
        "tier_policy", "scope COMMISSION requires the 'commission' tier, not 'actuate'"
    )
    r = estop_clear_tool(ctx)
    assert r["ok"] is False
    assert r["error"]["deny"] == "tier_policy"
    assert ctx.estop.is_set()  # still latched


def test_a_system_gate_no_longer_decides_the_clear(fixtures_dir, gateway_env):
    """The old in-process `system` gate is gone: the commission tier at the
    gateway is the check. A declared gate neither blocks the request nor is
    satisfied by anything the caller passes."""
    ctx = load_context(fixtures_dir / MANIFEST)
    ctx.parsed.frontmatter["safety"].setdefault("hitl_gates", []).append(
        {"scope": "system", "require_auth": True}
    )
    ctx.spec = RobotSpec.from_parsed(ctx.parsed)
    estop_tool(ctx)
    gateway_env.deny(
        "tier_policy", "scope COMMISSION requires the 'commission' tier, not 'actuate'"
    )
    r = estop_clear_tool(ctx)
    assert r["ok"] is False
    assert gateway_env.bodies[-1]["scope"] == "COMMISSION"
    assert ctx.estop.is_set()


def test_estop_clear_without_a_gateway_sends_nothing_and_keeps_the_latch(fixtures_dir):
    ctx = load_context(fixtures_dir / MANIFEST)
    ctx.estop.set()
    r = estop_clear_tool(ctx)
    assert r["ok"] is False
    assert r["error"]["reason"] == "gateway_not_configured"
    assert ctx.estop.is_set()
