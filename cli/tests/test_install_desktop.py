"""Tests for robot-md install-desktop."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from robot_md.install_desktop import SERVER_KEY, default_config_path, install


@pytest.fixture
def manifest(tmp_path: Path) -> Path:
    p = tmp_path / "ROBOT.md"
    p.write_text("---\nmetadata:\n  robot_name: bob\n---\n# bob\n")
    return p


def test_default_config_path_is_platform_specific():
    # Just assert it returns SOMETHING under the user's home with the
    # expected filename. Per-OS branch coverage is exercised by the
    # function's type signature and the runtime test.
    p = default_config_path()
    assert p.name == "claude_desktop_config.json"
    assert "Claude" in p.parts


def test_install_creates_new_config(tmp_path, manifest):
    cfg = tmp_path / "claude_desktop_config.json"
    result = install(manifest, config_path=cfg)
    assert result.status == "wrote"
    assert cfg.exists()
    data = json.loads(cfg.read_text())
    entry = data["mcpServers"][SERVER_KEY]
    assert entry["command"] == "npx"
    assert "-y" in entry["args"]
    assert "robot-md-mcp" in entry["args"]
    # Manifest path in args is absolute.
    assert str(manifest.resolve()) in entry["args"]


def test_install_preserves_existing_servers(tmp_path, manifest):
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "filesystem": {
                        "command": "npx",
                        "args": ["@modelcontextprotocol/server-filesystem", "/tmp"],
                    },
                    "github": {"command": "npx", "args": ["@modelcontextprotocol/server-github"]},
                }
            }
        )
    )
    result = install(manifest, config_path=cfg)
    assert result.status == "added"
    data = json.loads(cfg.read_text())
    assert set(data["mcpServers"].keys()) == {"filesystem", "github", SERVER_KEY}
    # Existing entries unchanged.
    assert data["mcpServers"]["filesystem"]["args"] == [
        "@modelcontextprotocol/server-filesystem",
        "/tmp",
    ]


def test_install_unchanged_when_entry_matches(tmp_path, manifest):
    cfg = tmp_path / "claude_desktop_config.json"
    install(manifest, config_path=cfg)
    # Second call should no-op.
    result = install(manifest, config_path=cfg)
    assert result.status == "unchanged"


def test_install_conflict_without_force(tmp_path, manifest):
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text(
        json.dumps(
            {
                "mcpServers": {
                    SERVER_KEY: {"command": "old-command", "args": ["old-args"]},
                }
            }
        )
    )
    result = install(manifest, config_path=cfg)
    assert result.status == "conflict"
    assert result.prior_entry == {"command": "old-command", "args": ["old-args"]}
    # File unchanged when conflict reported without force.
    data = json.loads(cfg.read_text())
    assert data["mcpServers"][SERVER_KEY]["command"] == "old-command"


def test_install_force_overwrites_conflicting_entry(tmp_path, manifest):
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text(json.dumps({"mcpServers": {SERVER_KEY: {"command": "old", "args": []}}}))
    result = install(manifest, config_path=cfg, force=True)
    assert result.status == "updated"
    assert result.prior_entry == {"command": "old", "args": []}
    data = json.loads(cfg.read_text())
    assert data["mcpServers"][SERVER_KEY]["command"] == "npx"


def test_install_rejects_invalid_json(tmp_path, manifest):
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text("{this is not json")
    with pytest.raises(ValueError, match="not valid JSON"):
        install(manifest, config_path=cfg)


def test_install_rejects_missing_manifest(tmp_path):
    cfg = tmp_path / "claude_desktop_config.json"
    with pytest.raises(FileNotFoundError):
        install(tmp_path / "nope.ROBOT.md", config_path=cfg)


def test_install_creates_parent_dirs(tmp_path, manifest):
    cfg = tmp_path / "a" / "b" / "c" / "claude_desktop_config.json"
    result = install(manifest, config_path=cfg)
    assert result.status == "wrote"
    assert cfg.exists()
