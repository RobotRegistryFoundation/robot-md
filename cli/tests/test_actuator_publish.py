"""Tests for robot_md.actuator.detect_package_metadata + publish helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from robot_md.__main__ import app
from robot_md.actuator import (
    actuator_publish_first_time,
    actuator_publish_version_update,
    build_registry_entry,
    detect_package_metadata,
    load_published_rpn,
    publish_record_path,
    record_published_rpn,
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


def test_publish_record_path_under_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    p = publish_record_path("feetech-arm")
    assert p == tmp_path / ".robot-md" / "published" / "feetech-arm.json"


def test_record_and_load_published_rpn_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    record_published_rpn(
        "feetech-arm", "RPN-000000000007", "https://x/v2/packages/RPN-000000000007"
    )
    rpn, url = load_published_rpn("feetech-arm")
    assert rpn == "RPN-000000000007"
    assert url == "https://x/v2/packages/RPN-000000000007"


def test_load_published_rpn_returns_none_for_unknown(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert load_published_rpn("nope") == (None, None)


def test_first_time_publish_calls_register(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    pkg = _scaffold_minimal_actuator(tmp_path, with_plugin=False)
    captured = {}

    def _fake_register(*, signed_body, timeout=10.0):
        captured["body"] = signed_body
        return {"rpn": "RPN-000000000007", "registered_at": "x", "record_url": "x"}

    monkeypatch.setattr("robot_md.actuator.register_package", _fake_register)
    monkeypatch.setattr("robot_md.actuator.load_or_mint_publisher_key", lambda u: _DummyKp())
    monkeypatch.setattr(
        "robot_md.actuator._sign",
        lambda fields, kp: {**fields, "sig": {"ml_dsa": "FAKE", "ed25519": "FAKE"}},
    )
    out = actuator_publish_first_time(pkg, github_user="alice")
    assert out["rpn"] == "RPN-000000000007"
    assert captured["body"]["name"] == "my-actuator"
    assert captured["body"]["package_type"] == "actuator"
    assert "sig" in captured["body"]
    rpn, _ = load_published_rpn("my-actuator")
    assert rpn == "RPN-000000000007"


def test_version_update_calls_append_version(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    pkg = _scaffold_minimal_actuator(tmp_path, with_plugin=False)
    record_published_rpn("my-actuator", "RPN-000000000007", "x")
    captured = {}

    def _fake_append(rpn, *, signed_body, timeout=10.0):
        captured["rpn"] = rpn
        captured["body"] = signed_body
        return {"rpn": rpn, "versions": []}

    monkeypatch.setattr("robot_md.actuator.append_version", _fake_append)
    monkeypatch.setattr("robot_md.actuator.load_or_mint_publisher_key", lambda u: _DummyKp())
    monkeypatch.setattr(
        "robot_md.actuator._sign",
        lambda fields, kp: {**fields, "sig": {"ml_dsa": "FAKE", "ed25519": "FAKE"}},
    )
    actuator_publish_version_update(pkg, github_user="alice")
    assert captured["rpn"] == "RPN-000000000007"
    assert "version" in captured["body"]
    assert "sig" in captured["body"]


class _DummyKp:
    pq_kid = "publisher-alice"
    pq_signing_pub = b"PUB"
    pq_signing_sec = b"SEC"
    ed25519_pub = b"EPUB"
    ed25519_sec = b"ESEC"
    ml_dsa = None


def test_publish_dry_run_first_time_prints_register_payload(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    pkg = _scaffold_minimal_actuator(tmp_path, with_plugin=False)
    monkeypatch.setattr("robot_md.actuator.load_or_mint_publisher_key", lambda u: _DummyKp())
    monkeypatch.setattr(
        "robot_md.actuator._sign",
        lambda fields, kp: {**fields, "sig": {"ml_dsa": "FAKE", "ed25519": "FAKE"}},
    )
    res = _runner.invoke(
        app,
        ["actuator", "publish", "--dry-run", "--package-dir", str(pkg), "--github-user", "alice"],
        env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"},
    )
    assert res.exit_code == 0, res.output
    assert "POST" in res.stdout
    assert "/v2/packages/register" in res.stdout
    assert "feetech-arm" in res.stdout or "my-actuator" in res.stdout
    assert "sig" in res.stdout


def test_publish_dry_run_version_update_prints_append_payload(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    pkg = _scaffold_minimal_actuator(tmp_path, with_plugin=False)
    record_published_rpn("my-actuator", "RPN-000000000007", "x")
    monkeypatch.setattr("robot_md.actuator.load_or_mint_publisher_key", lambda u: _DummyKp())
    monkeypatch.setattr(
        "robot_md.actuator._sign",
        lambda fields, kp: {**fields, "sig": {"ml_dsa": "FAKE", "ed25519": "FAKE"}},
    )
    res = _runner.invoke(
        app,
        ["actuator", "publish", "--dry-run", "--package-dir", str(pkg), "--github-user", "alice"],
        env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"},
    )
    assert res.exit_code == 0, res.output
    assert "/v2/packages/RPN-000000000007/versions" in res.stdout
