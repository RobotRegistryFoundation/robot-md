from __future__ import annotations

from robot_md.mcp.context import load_context
from robot_md.mcp.tools.estop import estop_tool


def test_estop_sets_flag(fixtures_dir):
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    assert not ctx.estop.is_set()
    result = estop_tool(ctx)
    assert result["ok"] is True
    assert result["set_at"] > 0
    assert ctx.estop.is_set()
