from __future__ import annotations

from robot_md.mcp.context import load_context
from robot_md.mcp.tools.validate import validate_tool


def test_validate_ok_shape(fixtures_dir):
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    result = validate_tool(ctx)
    assert result["ok"] is True
    assert "summary" in result
    assert isinstance(result["warnings"], list)
