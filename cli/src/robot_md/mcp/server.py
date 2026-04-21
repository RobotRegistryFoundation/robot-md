"""robot-md MCP server — stdio, registers render / validate / estop.

More tools (`execute_capability`, `execute_task`) are registered in later tasks.
"""

from __future__ import annotations

import sys
from pathlib import Path

from mcp.server.fastmcp import Context

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

    @server.tool()
    def vision_find(descriptor_id: str) -> dict:
        """Detect one declared object descriptor. Returns camera-frame XYZ (mm)."""
        from robot_md.mcp.tools.vision_find import vision_find_tool

        return vision_find_tool(ctx, descriptor_id=descriptor_id)

    @server.tool()
    def record_skill(
        skill_id: str,
        status: str = "ok",
        validated: list[str] | None = None,
        blocked_by: list[str] | None = None,
        notes: str | None = None,
    ) -> dict:
        """Append/upsert a learned_skills[] entry on the served ROBOT.md."""
        from robot_md.mcp.tools.record_skill import record_skill_tool

        return record_skill_tool(
            ctx,
            skill_id=skill_id,
            status=status,
            validated=validated,
            blocked_by=blocked_by,
            notes=notes,
        )

    @server.tool()
    async def discover(steps: list[dict], mcp_ctx: Context | None = None) -> dict:
        """Run the declarative discovery pipeline.

        Supported steps: capture, detect, probe_direction. See
        docs/superpowers/specs/2026-04-19-claude-triad-gap-analysis.md §8.

        FastMCP injects `mcp_ctx` for progress notifications; direct callers
        may omit it and `report_progress` will be skipped.
        """
        from robot_md.mcp.tools.discover import discover_tool

        return await discover_tool(ctx, steps=steps, mcp_ctx=mcp_ctx)

    from robot_md.mcp.resources import _sanitize_robot_name

    robot_name = _sanitize_robot_name(ctx.spec.metadata.robot_name if ctx.spec else None)

    @server.resource(f"robot-md://{robot_name}/learned_skills", mime_type="application/json")
    def _resource_learned_skills() -> str:
        import json

        from robot_md.mcp.resources import learned_skills as _ls

        return json.dumps(_ls(ctx), indent=2)

    @server.resource(f"robot-md://{robot_name}/calibration_status", mime_type="application/json")
    def _resource_calibration_status() -> str:
        import json

        from robot_md.mcp.resources import calibration_status as _cs

        return json.dumps(_cs(ctx), indent=2)

    @server.resource(f"robot-md://{robot_name}/poses", mime_type="application/json")
    def _resource_poses() -> str:
        import json

        from robot_md.mcp.resources import poses as _poses

        return json.dumps(_poses(ctx), indent=2)

    @server.resource(f"robot-md://{robot_name}/recent_invocations", mime_type="application/json")
    def _resource_recent_invocations() -> str:
        import json

        from robot_md.mcp.resources import recent_invocations as _ri

        return json.dumps(_ri(ctx), indent=2)

    @server.resource(f"robot-md://{robot_name}/recent_errors", mime_type="application/json")
    def _resource_recent_errors() -> str:
        import json

        from robot_md.mcp.resources import recent_errors as _re

        return json.dumps(_re(ctx), indent=2)

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
