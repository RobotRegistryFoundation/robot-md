"""Phase: register the stdio MCP server with Claude Code."""

from __future__ import annotations

from pathlib import Path

from robot_md.init_phases import PhaseResult
from robot_md.install_mcp_claude_code import Scope, add
from robot_md.parser import parse_file


def phase_install_mcp(
    manifest_path: Path,
    *,
    command: str = "robot-md-mcp",
    scope: Scope = "local",
) -> PhaseResult:
    """Derive the MCP server name from the manifest and delegate to `add`.

    Server name is `robot-md-<robot_name>` so multiple robots coexist
    cleanly in one `~/.claude.json`. Returns a `PhaseResult`; never raises.
    """
    try:
        parsed = parse_file(manifest_path)
    except Exception as e:
        return PhaseResult(
            phase="install_mcp",
            status="failed",
            message=f"could not read manifest {manifest_path}: {e}",
            detail={"reason": "parse_error", "error": str(e)},
        )

    robot_name = (parsed.frontmatter.get("metadata") or {}).get("robot_name")
    if not robot_name:
        return PhaseResult(
            phase="install_mcp",
            status="failed",
            message="manifest has no metadata.robot_name; cannot derive server name",
            detail={"reason": "missing_robot_name"},
        )

    server_name = f"robot-md-{robot_name}"
    return add(server_name, manifest_path, command=command, scope=scope)
