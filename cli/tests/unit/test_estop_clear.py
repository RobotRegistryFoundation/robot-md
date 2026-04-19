from __future__ import annotations

from robot_md.mcp.context import load_context
from robot_md.mcp.tools.estop import estop_clear_tool, estop_tool


def test_estop_clear_clears_flag(fixtures_dir):
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    estop_tool(ctx)
    assert ctx.estop.is_set()
    r = estop_clear_tool(ctx, confirm_token=None)
    # Without HITL gate in fixture, token unnecessary
    assert r["ok"] is True
    assert not ctx.estop.is_set()
    assert r["cleared_at"] > 0


def test_estop_clear_blocked_without_token_when_gate_declared(fixtures_dir):
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    # Inject a system-scope HITL gate (matching the clear path)
    ctx.parsed.frontmatter["safety"].setdefault("hitl_gates", []).append(
        {"scope": "system", "require_auth": True}
    )
    from robot_md.robot_spec import RobotSpec
    ctx.spec = RobotSpec.from_parsed(ctx.parsed)
    estop_tool(ctx)

    r = estop_clear_tool(ctx, confirm_token=None)
    assert r["ok"] is False
    assert r["error"]["reason"] == "hitl_gate"
    assert ctx.estop.is_set()  # still latched


def test_estop_clear_succeeds_with_token_when_gated(fixtures_dir):
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    ctx.parsed.frontmatter["safety"].setdefault("hitl_gates", []).append(
        {"scope": "system", "require_auth": True}
    )
    from robot_md.robot_spec import RobotSpec
    ctx.spec = RobotSpec.from_parsed(ctx.parsed)
    estop_tool(ctx)

    r = estop_clear_tool(ctx, confirm_token="anything")
    assert r["ok"] is True
    assert not ctx.estop.is_set()
