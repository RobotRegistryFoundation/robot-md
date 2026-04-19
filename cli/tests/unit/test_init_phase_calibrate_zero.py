"""Unit tests for phase_calibrate_zero — TTY/hardware gates + success/failure paths."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


def _write_feetech_manifest(path: Path) -> None:
    path.write_text(
        "---\n"
        "metadata:\n  robot_name: bob\n"
        "drivers:\n  - id: arm\n    protocol: feetech\n    port: /dev/ttyACM0\n"
        "---\n\n# bob\n"
    )


def test_skipped_when_stdin_not_tty(tmp_path):
    from robot_md.init_phases import phase_calibrate_zero

    manifest = tmp_path / "ROBOT.md"
    _write_feetech_manifest(manifest)

    with patch("robot_md.init_phases.calibrate_zero.sys.stdin.isatty", return_value=False):
        result = phase_calibrate_zero(manifest)

    assert result.status == "skipped"
    assert "tty" in result.message.lower()


def test_skipped_when_hardware_absent(tmp_path):
    from robot_md.init_phases import phase_calibrate_zero

    manifest = tmp_path / "ROBOT.md"
    _write_feetech_manifest(manifest)

    with (
        patch("robot_md.init_phases.calibrate_zero.sys.stdin.isatty", return_value=True),
        patch("robot_md.init_phases.calibrate_zero._probe_feetech_port", return_value=False),
    ):
        result = phase_calibrate_zero(manifest)

    assert result.status == "skipped"
    assert "hardware" in result.message.lower() or "/dev/ttyACM0" in result.message


def test_skipped_when_operator_declines(tmp_path):
    from robot_md.init_phases import phase_calibrate_zero

    manifest = tmp_path / "ROBOT.md"
    _write_feetech_manifest(manifest)

    with (
        patch("robot_md.init_phases.calibrate_zero.sys.stdin.isatty", return_value=True),
        patch("robot_md.init_phases.calibrate_zero._probe_feetech_port", return_value=True),
        patch("robot_md.init_phases.calibrate_zero.input", return_value="n"),
    ):
        result = phase_calibrate_zero(manifest)

    assert result.status == "skipped"
    assert "declined" in result.message.lower() or "skip" in result.message.lower()


def test_ok_runs_cli_calibrate_zero(tmp_path):
    from robot_md.init_phases import phase_calibrate_zero

    manifest = tmp_path / "ROBOT.md"
    _write_feetech_manifest(manifest)

    with (
        patch("robot_md.init_phases.calibrate_zero.sys.stdin.isatty", return_value=True),
        patch("robot_md.init_phases.calibrate_zero._probe_feetech_port", return_value=True),
        patch("robot_md.init_phases.calibrate_zero.input", return_value="y"),
        patch("robot_md.init_phases.calibrate_zero.cli_calibrate_zero", return_value=0) as run,
    ):
        result = phase_calibrate_zero(manifest)

    assert result.status == "ok"
    run.assert_called_once_with(str(manifest))


def test_failed_when_cli_returns_nonzero(tmp_path):
    from robot_md.init_phases import phase_calibrate_zero

    manifest = tmp_path / "ROBOT.md"
    _write_feetech_manifest(manifest)

    with (
        patch("robot_md.init_phases.calibrate_zero.sys.stdin.isatty", return_value=True),
        patch("robot_md.init_phases.calibrate_zero._probe_feetech_port", return_value=True),
        patch("robot_md.init_phases.calibrate_zero.input", return_value="y"),
        patch("robot_md.init_phases.calibrate_zero.cli_calibrate_zero", return_value=1),
    ):
        result = phase_calibrate_zero(manifest)

    assert result.status == "failed"
    assert result.detail and result.detail.get("exit_code") == 1


def test_bypass_prompt_when_prompt_false(tmp_path):
    from robot_md.init_phases import phase_calibrate_zero

    manifest = tmp_path / "ROBOT.md"
    _write_feetech_manifest(manifest)

    with (
        patch("robot_md.init_phases.calibrate_zero.sys.stdin.isatty", return_value=True),
        patch("robot_md.init_phases.calibrate_zero._probe_feetech_port", return_value=True),
        patch("robot_md.init_phases.calibrate_zero.input") as input_mock,
        patch("robot_md.init_phases.calibrate_zero.cli_calibrate_zero", return_value=0),
    ):
        phase_calibrate_zero(manifest, prompt=False)

    input_mock.assert_not_called()
