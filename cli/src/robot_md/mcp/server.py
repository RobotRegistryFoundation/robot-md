"""robot-md MCP server — stdio, registers render / validate / estop.

More tools (`execute_capability`, `execute_task`) are registered in later tasks.
"""

from __future__ import annotations

import sys
from pathlib import Path

from robot_md.mcp.context import McpContext, load_context
from robot_md.mcp.tools.estop import estop_clear_tool, estop_tool
from robot_md.mcp.tools.render import render_tool
from robot_md.mcp.tools.validate import validate_tool


def build_server(ctx: McpContext):
    """Build a FastMCP server with the render/validate/estop tools bound to ctx."""
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("robot-md")

    @server.tool()
    def render() -> str:
        """Strip prose and return the frontmatter as canonical YAML."""
        return render_tool(ctx)

    @server.tool()
    def validate() -> dict:
        """Validate the served ROBOT.md against the v1 schema and body rules."""
        return validate_tool(ctx)

    @server.tool()
    def estop() -> dict:
        """Set the software E-stop for this server session."""
        return estop_tool(ctx)

    @server.tool()
    def estop_clear(confirm_token: str | None = None) -> dict:
        """Clear the software E-stop. Gated by the `system` HITL scope by default."""
        return estop_clear_tool(ctx, confirm_token=confirm_token)

    @server.tool()
    def execute_capability(
        capability: str,
        args: dict | None = None,
        dry_run: bool = False,
        confirm_token: str | None = None,
    ) -> dict:
        """Execute a declared capability against the resolved backend."""
        from robot_md.mcp.tools.execute_capability import execute_capability_tool

        return execute_capability_tool(
            ctx,
            capability=capability,
            args=dict(args or {}),
            dry_run=dry_run,
            confirm_token=confirm_token,
        )

    @server.tool()
    def execute_task(
        prompt: str,
        context: dict | None = None,
        dry_run: bool = False,
        confirm_token: str | None = None,
    ) -> dict:
        """Decompose a natural-language task into capability steps and run them."""
        from robot_md.mcp.tools.execute_task import execute_task_tool

        return execute_task_tool(
            ctx,
            prompt=prompt,
            context=context,
            dry_run=dry_run,
            confirm_token=confirm_token,
        )

    return server


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: robot-md-mcp <ROBOT.md>", file=sys.stderr)
        return 2
    manifest = Path(sys.argv[1])
    try:
        ctx = load_context(manifest)
    except Exception as e:
        print(f"robot-md-mcp: fatal: {e}", file=sys.stderr)
        return 1
    server = build_server(ctx)
    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
