"""MCP tool: estop — set the process-wide estop flag."""

from __future__ import annotations

from robot_md.mcp.context import McpContext


def estop_tool(ctx: McpContext) -> dict:
    ts = ctx.estop.set()
    return {"ok": True, "set_at": ts}
