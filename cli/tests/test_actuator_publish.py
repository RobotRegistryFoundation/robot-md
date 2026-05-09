"""Tests for robot_md.actuator.detect_package_metadata + publish helpers."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from robot_md.actuator import (
    build_registry_entry,
    detect_package_metadata,
)


def _scaffold_minimal_actuator(parent: Path, *, with_plugin: bool) -> Path:
    pkg = parent / "my-actuator"
    pkg.mkdir()
    (pkg / "pyproject.toml").write_text("""\
[project]
name = "my-actuator"
version = "0.2.0"
description = "Example actuator"

[project.urls]
Repository = "https://github.com/example/my-actuator"
""")
    skills_dir = pkg / "src" / "my_actuator" / "skills"
    skills_dir.mkdir(parents=True)
    (skills_dir / "using-my-actuator.SKILL.md").write_text("""\
---
name: using-my-actuator
hardware_tags: [arm, feetech]
manifest_signals: [SO-ARM101]
---

# my-actuator
""")
    if with_plugin:
        plugin_dir = pkg / "claude-plugin" / ".claude-plugin"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.json").write_text(json.dumps({
            "name": "my-actuator",
            "version": "0.2.0",
        }))
    return pkg


def test_detect_metadata_reads_pyproject_and_skill(tmp_path):
    pkg = _scaffold_minimal_actuator(tmp_path, with_plugin=False)
    meta = detect_package_metadata(pkg)
    assert meta["name"] == "my-actuator"
    assert meta["version"] == "0.2.0"
    assert meta["description"] == "Example actuator"
    assert meta["repository_url"] == "https://github.com/example/my-actuator"
    assert meta["hardware_tags"] == ["arm", "feetech"]
    assert meta["manifest_signals"] == ["SO-ARM101"]
    assert meta["has_plugin_layout"] is False
    assert meta["skill_files"] == ["using-my-actuator.SKILL.md"]


def test_detect_metadata_finds_plugin_layout(tmp_path):
    pkg = _scaffold_minimal_actuator(tmp_path, with_plugin=True)
    meta = detect_package_metadata(pkg)
    assert meta["has_plugin_layout"] is True


def test_detect_metadata_raises_on_missing_pyproject(tmp_path):
    with pytest.raises(FileNotFoundError):
        detect_package_metadata(tmp_path)


def test_build_registry_entry_without_plugin():
    meta = {
        "name": "rpi-cam", "version": "1.0",
        "description": "Pi camera driver",
        "repository_url": "https://github.com/me/rpi-cam",
        "hardware_tags": ["raspberry-pi", "camera"],
        "manifest_signals": [],
        "has_plugin_layout": False,
        "skill_files": ["using-rpi-cam.SKILL.md"],
    }
    e = build_registry_entry(meta, publisher="github:me", published_at="2026-05-09T00:00:00Z")
    assert e["type"] == "actuator"
    assert e["name"] == "rpi-cam"
    assert e["version"] == "1.0"
    assert e["install"]["package"] == "rpi-cam"
    assert e["install"]["post_install"] == "robot-md install-skill rpi-cam"
    assert "plugin_marketplace_entry" not in e
    assert e["verified"] is False


def test_build_registry_entry_with_plugin_includes_marketplace_block():
    meta = {
        "name": "feetech-arm", "version": "0.5",
        "description": "Feetech arm",
        "repository_url": "https://github.com/me/feetech-arm",
        "hardware_tags": ["arm"], "manifest_signals": ["SO-ARM101"],
        "has_plugin_layout": True,
        "skill_files": ["using-feetech-arm.SKILL.md"],
    }
    e = build_registry_entry(
        meta, publisher="github:me", published_at="2026-05-09T00:00:00Z",
    )
    assert e["plugin_marketplace_entry"]["marketplace"] == "robotregistryfoundation"
    assert e["plugin_marketplace_entry"]["plugin_name"] == "feetech-arm"
    assert e["plugin_marketplace_entry"]["install_command"] == "/plugin install feetech-arm@robotregistryfoundation"
