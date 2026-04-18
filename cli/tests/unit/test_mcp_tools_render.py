from __future__ import annotations

from robot_md.mcp.context import load_context
from robot_md.mcp.tools.render import render_tool


def test_render_returns_frontmatter_yaml(fixtures_dir):
    ctx = load_context(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    out = render_tool(ctx)
    assert "rcan_version" in out
    assert "test-bot" in out
