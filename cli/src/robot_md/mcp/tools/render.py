"""MCP tool: render — canonical YAML frontmatter."""

from __future__ import annotations

from robot_md.mcp.context import McpContext
from robot_md.render import render_yaml


def render_tool(ctx: McpContext) -> str:
    return render_yaml(ctx.parsed)
