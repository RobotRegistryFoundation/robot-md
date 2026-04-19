"""Unit tests for the claude-mcp-add subprocess wrapper."""
from __future__ import annotations

import subprocess
from unittest.mock import patch


def test_add_returns_failed_when_claude_not_in_path(tmp_path):
    from robot_md.install_mcp_claude_code import add

    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("---\n---\n")

    with patch("robot_md.install_mcp_claude_code.shutil.which", return_value=None):
        result = add("robot-md-bob", manifest)

    assert result.status == "failed"
    assert "claude" in result.message.lower()
    assert result.detail and result.detail.get("reason") == "claude_not_in_path"


def test_add_returns_ok_on_successful_subprocess(tmp_path):
    from robot_md.install_mcp_claude_code import add

    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("---\n---\n")

    fake = subprocess.CompletedProcess(args=[], returncode=0, stdout="Added", stderr="")
    with (
        patch("robot_md.install_mcp_claude_code.shutil.which", return_value="/usr/bin/claude"),
        patch("robot_md.install_mcp_claude_code.subprocess.run", return_value=fake) as run,
    ):
        result = add("robot-md-bob", manifest, command="robot-md-mcp")

    assert result.status == "ok"
    assert result.detail and result.detail.get("server_name") == "robot-md-bob"
    args = run.call_args.args[0]
    # claude mcp add <name> <cmd> <arg1> ...
    assert args[0] == "/usr/bin/claude"
    assert "mcp" in args and "add" in args
    assert "robot-md-bob" in args
    assert "robot-md-mcp" in args
    assert str(manifest) in args


def test_add_treats_already_registered_as_ok(tmp_path):
    from robot_md.install_mcp_claude_code import add

    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("---\n---\n")

    fake = subprocess.CompletedProcess(
        args=[],
        returncode=1,
        stdout="",
        stderr="server with name 'robot-md-bob' already exists",
    )
    with (
        patch("robot_md.install_mcp_claude_code.shutil.which", return_value="/usr/bin/claude"),
        patch("robot_md.install_mcp_claude_code.subprocess.run", return_value=fake),
    ):
        result = add("robot-md-bob", manifest)

    assert result.status == "ok"
    assert result.detail and result.detail.get("already_registered") is True


def test_add_returns_failed_on_other_subprocess_error(tmp_path):
    from robot_md.install_mcp_claude_code import add

    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("---\n---\n")

    fake = subprocess.CompletedProcess(
        args=[],
        returncode=2,
        stdout="",
        stderr="unexpected failure",
    )
    with (
        patch("robot_md.install_mcp_claude_code.shutil.which", return_value="/usr/bin/claude"),
        patch("robot_md.install_mcp_claude_code.subprocess.run", return_value=fake),
    ):
        result = add("robot-md-bob", manifest)

    assert result.status == "failed"
    assert "unexpected" in result.message or "failed" in result.message


def test_add_scope_passed_through(tmp_path):
    from robot_md.install_mcp_claude_code import add

    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("---\n---\n")

    fake = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    with (
        patch("robot_md.install_mcp_claude_code.shutil.which", return_value="/usr/bin/claude"),
        patch("robot_md.install_mcp_claude_code.subprocess.run", return_value=fake) as run,
    ):
        add("robot-md-bob", manifest, scope="user")

    args = run.call_args.args[0]
    assert "--scope" in args
    assert args[args.index("--scope") + 1] == "user"
