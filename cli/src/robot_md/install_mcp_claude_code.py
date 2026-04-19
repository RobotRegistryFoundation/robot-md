"""Thin wrapper around `claude mcp add` for `robot-md init --install-mcp`.

Shells out via subprocess. Detects `claude` missing from PATH and
"already registered" as non-errors (returns ok). Never raises.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Literal

from robot_md.init_phases import PhaseResult

Scope = Literal["local", "user", "project"]


def add(
    server_name: str,
    manifest_path: Path,
    *,
    command: str = "robot-md-mcp",
    scope: Scope = "local",
) -> PhaseResult:
    """Register a stdio MCP server with Claude Code via `claude mcp add`.

    Idempotent: if the server is already registered at this scope,
    returns `status="ok"` with `detail["already_registered"] = True`.
    Returns `status="failed"` with a clear message if the `claude` CLI
    is not available or the subprocess fails for another reason.
    """
    claude_bin = shutil.which("claude")
    if claude_bin is None:
        return PhaseResult(
            phase="install_mcp",
            status="failed",
            message="`claude` CLI not in PATH — install Claude Code or run "
            f"`claude mcp add {server_name} -- {command} {manifest_path}` manually.",
            detail={"reason": "claude_not_in_path"},
        )

    args = [
        claude_bin,
        "mcp",
        "add",
        server_name,
        "--scope",
        scope,
        "--",
        command,
        str(manifest_path),
    ]

    try:
        proc = subprocess.run(args, check=False, capture_output=True, text=True)
    except OSError as e:
        return PhaseResult(
            phase="install_mcp",
            status="failed",
            message=f"subprocess failed to launch `claude`: {e}",
            detail={"reason": "subprocess_exec_failed", "error": str(e)},
        )

    if proc.returncode == 0:
        return PhaseResult(
            phase="install_mcp",
            status="ok",
            message=f"registered '{server_name}' ({scope} scope)",
            detail={"server_name": server_name, "scope": scope, "already_registered": False},
        )

    combined = (proc.stderr or "") + (proc.stdout or "")
    if "already exists" in combined.lower() or "already registered" in combined.lower():
        return PhaseResult(
            phase="install_mcp",
            status="ok",
            message=f"'{server_name}' already registered ({scope} scope)",
            detail={"server_name": server_name, "scope": scope, "already_registered": True},
        )

    return PhaseResult(
        phase="install_mcp",
        status="failed",
        message=f"`claude mcp add` failed (exit {proc.returncode}): {combined.strip()[:200]}",
        detail={
            "reason": "claude_add_failed",
            "returncode": proc.returncode,
            "stderr": proc.stderr,
            "stdout": proc.stdout,
        },
    )
