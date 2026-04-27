"""DEPRECATED: install_mcp phase no longer wires the MCP server.

Per SP1 simplification revision R1, the `robot-md` plugin's .mcp.json
declares the Python `robot-md mcp` server directly. init no longer needs
to run `claude mcp add`. This phase is preserved as a no-op for backward
compatibility — old scripts calling `phase_install_mcp(...)` keep
working but get a clear "skipped" result.

Operators upgrade their MCP wiring via:
  1. `claude plugin install robot-md` (or `/plugin update robot-md`)
  2. `pip install 'robot-md[hardware]'`
  3. `/mcp` → Reconnect `robot-md`

For non-plugin operators, `install_mcp_claude_code.add(...)` is still
exported and can be called manually.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from robot_md.init_phases import PhaseResult

# Kept as a type alias so external callers importing Scope from this
# module continue to work after the deprecation.
Scope = Literal["local", "user", "project"]


def phase_install_mcp(
    manifest_path: Path,
    *,
    command: str = "robot-md-mcp",
    scope: Scope = "local",
) -> PhaseResult:
    """No-op deprecation. Returns status=skipped with explanation.

    Signature preserved for backward compat — `command` and `scope`
    args are ignored.
    """
    return PhaseResult(
        phase="install_mcp",
        status="skipped",
        message=(
            "MCP wiring is handled by the robot-md plugin's .mcp.json. "
            "After `pip install 'robot-md[hardware]'`, run `/mcp` → "
            "Reconnect `robot-md` (or restart Claude Code). "
            "No per-robot `claude mcp add` needed."
        ),
        detail={
            "deprecated_in": "1.2.0",
            "reason": "plugin_handles_mcp",
            "ignored_args": {"command": command, "scope": scope},
        },
    )
