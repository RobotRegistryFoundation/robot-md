"""Tests for robot_md.actuator.detect_package_metadata + publish helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from robot_md.__main__ import app
from robot_md.actuator import (
    build_registry_entry,
    detect_package_metadata,
)

_runner = CliRunner()


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
        (plugin_dir / "plugin.json").write_text(
            json.dumps(
                {
                    "name": "my-actuator",
                    "version": "0.2.0",
                }
            )
        )
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
        "name": "rpi-cam",
        "version": "1.0",
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
        "name": "feetech-arm",
        "version": "0.5",
        "description": "Feetech arm",
        "repository_url": "https://github.com/me/feetech-arm",
        "hardware_tags": ["arm"],
        "manifest_signals": ["SO-ARM101"],
        "has_plugin_layout": True,
        "skill_files": ["using-feetech-arm.SKILL.md"],
    }
    e = build_registry_entry(
        meta,
        publisher="github:me",
        published_at="2026-05-09T00:00:00Z",
    )
    assert e["plugin_marketplace_entry"]["marketplace"] == "robotregistryfoundation"
    assert e["plugin_marketplace_entry"]["plugin_name"] == "feetech-arm"
    assert (
        e["plugin_marketplace_entry"]["install_command"]
        == "/plugin install feetech-arm@robotregistryfoundation"
    )


def test_publish_dry_run_no_plugin_emits_one_pr_payload(tmp_path):
    pkg = _scaffold_minimal_actuator(tmp_path, with_plugin=False)
    res = _runner.invoke(
        app,
        ["actuator", "publish", "--dry-run", "--package-dir", str(pkg)],
        env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"},
    )
    assert res.exit_code == 0, res.output
    assert "robot-md" in res.stdout
    assert "site/actuators/index.json" in res.stdout
    assert "claude-code-plugins" not in res.stdout


def test_publish_dry_run_with_plugin_emits_two_pr_payloads(tmp_path):
    pkg = _scaffold_minimal_actuator(tmp_path, with_plugin=True)
    res = _runner.invoke(
        app,
        ["actuator", "publish", "--dry-run", "--package-dir", str(pkg)],
        env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"},
    )
    assert res.exit_code == 0, res.output
    assert "claude-code-plugins" in res.stdout
    assert "marketplace.json" in res.stdout
    assert "site/actuators/index.json" in res.stdout


def test_publish_dry_run_missing_pyproject_errors(tmp_path):
    res = _runner.invoke(
        app,
        ["actuator", "publish", "--dry-run", "--package-dir", str(tmp_path)],
        env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"},
    )
    assert res.exit_code != 0
    assert "pyproject.toml" in res.output.lower()


def test_open_registry_pr_writes_entry_and_calls_gh(tmp_path, monkeypatch):
    from robot_md.actuator import open_registry_pr

    calls: list[list[str]] = []
    pr_url = "https://github.com/RobotRegistryFoundation/robot-md/pull/999"

    def _fake_run(cmd, *args, **kwargs):
        calls.append(cmd)

        class _R:
            stdout = pr_url if cmd[:2] == ["gh", "pr"] else ""
            returncode = 0

        return _R()

    monkeypatch.setattr("robot_md.actuator.subprocess.run", _fake_run)
    monkeypatch.setenv("ROBOT_MD_PUBLISH_WORKTREE", str(tmp_path / "wt"))
    entry = {"type": "actuator", "name": "x", "version": "1"}
    out = open_registry_pr(entry)
    assert out == pr_url
    invoked = [c[0] for c in calls if c]
    assert "gh" in invoked
    assert "git" in invoked


def test_open_marketplace_pr_emits_correct_title(tmp_path, monkeypatch):
    from robot_md.actuator import open_marketplace_pr

    pr_url = "https://github.com/RobotRegistryFoundation/claude-code-plugins/pull/42"
    titles_seen: list[str] = []

    def _fake_run(cmd, *args, **kwargs):
        if cmd[:3] == ["gh", "pr", "create"]:
            i = cmd.index("--title")
            titles_seen.append(cmd[i + 1])

        class _R:
            stdout = pr_url if cmd[:2] == ["gh", "pr"] else ""
            returncode = 0

        return _R()

    monkeypatch.setattr("robot_md.actuator.subprocess.run", _fake_run)
    monkeypatch.setenv("ROBOT_MD_PUBLISH_WORKTREE", str(tmp_path / "wt"))
    out = open_marketplace_pr({"name": "feetech-arm", "version": "0.5"})
    assert out == pr_url
    assert any("feetech-arm" in t for t in titles_seen)
