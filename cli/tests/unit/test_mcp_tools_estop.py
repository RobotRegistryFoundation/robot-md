from __future__ import annotations

from robot_md.mcp.context import load_context
from robot_md.mcp.tools.estop import estop_tool


def test_estop_latches_and_sends_the_gateway_stop(fixtures_dir, gateway_env):
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    assert not ctx.estop.is_set()
    result = estop_tool(ctx)
    assert result["ok"] is True
    assert result["stop"] == "stopped"
    assert result["set_at"] > 0
    assert ctx.estop.is_set()
    assert len(gateway_env.requests) == 1
    assert gateway_env.bodies[0]["tool_name"] == "arm.estop"


def test_estop_latches_this_server_even_with_no_gateway(fixtures_dir):
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    result = estop_tool(ctx)
    assert result["ok"] is False
    assert result["stop"] == "stop_not_confirmed"
    assert "hardware stop" in result["message"]
    assert ctx.estop.is_set()
