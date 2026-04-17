"""Tests for the robot-md CLI entry point via typer's testing helpers."""

from __future__ import annotations

from typer.testing import CliRunner

from robot_md.__main__ import app

runner = CliRunner()


def test_cli_help_shows_three_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for verb in ("validate", "render", "context"):
        assert verb in result.stdout


def test_cli_validate_valid_file(fixtures_dir):
    path = fixtures_dir / "valid" / "minimal.ROBOT.md"
    result = runner.invoke(app, ["validate", str(path)])
    assert result.exit_code == 0, result.stdout


def test_cli_validate_schema_violation(fixtures_dir):
    path = fixtures_dir / "invalid" / "missing-safety.ROBOT.md"
    result = runner.invoke(app, ["validate", str(path)])
    assert result.exit_code == 2, result.stdout


def test_cli_validate_file_not_found():
    result = runner.invoke(app, ["validate", "/nonexistent/path.md"])
    assert result.exit_code == 1


def test_cli_render_emits_yaml(fixtures_dir):
    path = fixtures_dir / "valid" / "minimal.ROBOT.md"
    result = runner.invoke(app, ["render", str(path)])
    assert result.exit_code == 0
    # Output should be YAML, starting with rcan_version
    assert "rcan_version: '3.0'" in result.stdout or 'rcan_version: "3.0"' in result.stdout


def test_cli_context_emits_markdown(fixtures_dir):
    path = fixtures_dir / "valid" / "minimal.ROBOT.md"
    result = runner.invoke(app, ["context", str(path)])
    assert result.exit_code == 0
    assert "# Robot context" in result.stdout
    assert "test-bot" in result.stdout


def test_cli_version_flag():
    from robot_md import __version__

    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout
    assert "robot-md" in result.stdout
