"""robot-md install-desktop — wire ROBOT.md into the Claude Desktop app.

Claude Desktop (the macOS/Windows Anthropic app) reads MCP server
configuration from a `claude_desktop_config.json` file. Locations:

- macOS:   ~/Library/Application Support/Claude/claude_desktop_config.json
- Windows: %APPDATA%/Claude/claude_desktop_config.json
- Linux:   ~/.config/Claude/claude_desktop_config.json  (best-effort guess)

This module locates the correct file, merge-adds a `robot-md` server
entry that runs `npx -y robot-md-mcp <absolute-path-to-ROBOT.md>` via
stdio, and preserves any existing `mcpServers` entries.
"""

from __future__ import annotations

import json
import os
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SERVER_KEY = "robot-md"


def default_config_path() -> Path:
    """Return the Claude Desktop config path for the current OS.

    Does not check that the file exists. Caller is responsible for
    creating parent dirs if needed.
    """
    system = platform.system()
    if system == "Darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "Claude"
            / "claude_desktop_config.json"
        )
    if system == "Windows":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / "Claude" / "claude_desktop_config.json"
    # Linux / unknown — best-effort guess. Claude Desktop has no official
    # Linux build as of 2026-04; some users run it via wine or snap.
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "Claude" / "claude_desktop_config.json"


@dataclass
class InstallResult:
    """What happened. Status words: 'wrote' (new file), 'added' (new entry
    in existing file), 'updated' (replaced existing robot-md entry),
    'unchanged' (entry already matched). Path is the config file touched."""

    status: str
    path: Path
    prior_entry: dict[str, Any] | None = None


def _build_entry(manifest_path: Path) -> dict[str, Any]:
    """Return the `mcpServers.robot-md` entry for this manifest.

    Uses `npx -y robot-md-mcp` so the user doesn't need a global install;
    npx pulls the latest wheel on first run and caches it. Absolute path
    is required because Claude Desktop launches from an unspecified CWD.
    """
    absolute = manifest_path.resolve()
    return {
        "command": "npx",
        "args": ["-y", "robot-md-mcp", str(absolute)],
    }


def install(
    manifest_path: Path,
    *,
    config_path: Path | None = None,
    force: bool = False,
) -> InstallResult:
    """Add or refresh the robot-md entry in Claude Desktop's config.

    Existing entries for `robot-md` are left alone unless `force=True`
    OR the computed entry differs from what's already there. All other
    `mcpServers` entries are preserved.

    Raises FileNotFoundError if `manifest_path` doesn't exist.
    """
    if not manifest_path.exists():
        raise FileNotFoundError(f"{manifest_path} does not exist")

    cfg_path = config_path or default_config_path()
    new_entry = _build_entry(manifest_path)

    if cfg_path.exists():
        try:
            data = json.loads(cfg_path.read_text())
        except json.JSONDecodeError as e:
            raise ValueError(f"{cfg_path} is not valid JSON — refusing to corrupt it: {e}") from e
        if not isinstance(data, dict):
            raise ValueError(f"{cfg_path} top-level is not a JSON object")
        servers = data.setdefault("mcpServers", {})
        if not isinstance(servers, dict):
            raise ValueError(f"{cfg_path} `mcpServers` is not an object")

        prior = servers.get(SERVER_KEY)
        if prior == new_entry:
            return InstallResult(status="unchanged", path=cfg_path, prior_entry=prior)
        if prior is not None and not force:
            return InstallResult(status="conflict", path=cfg_path, prior_entry=prior)

        servers[SERVER_KEY] = new_entry
        cfg_path.write_text(json.dumps(data, indent=2) + "\n")
        return InstallResult(
            status="updated" if prior is not None else "added",
            path=cfg_path,
            prior_entry=prior,
        )

    # Fresh file.
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    data = {"mcpServers": {SERVER_KEY: new_entry}}
    cfg_path.write_text(json.dumps(data, indent=2) + "\n")
    return InstallResult(status="wrote", path=cfg_path)
