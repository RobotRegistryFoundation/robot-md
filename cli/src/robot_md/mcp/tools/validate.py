"""MCP tool: validate — schema + body rules + warnings."""

from __future__ import annotations

from robot_md.mcp.context import McpContext
from robot_md.validate import VALID, validate as validate_parsed


def validate_tool(ctx: McpContext) -> dict:
    result = validate_parsed(ctx.parsed)
    return {
        "ok": result.code == VALID,
        "summary": result.summary,
        "errors": list(result.errors),
        "warnings": list(result.warnings),
    }
