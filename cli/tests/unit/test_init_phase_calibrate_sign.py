"""Unit tests for phase_calibrate_sign — same gates as zero, separate phase name."""

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
    from robot_md.init_phases import phase_calibrate_sign

    manifest = tmp_path / "ROBOT.md"
    _write_feetech_manifest(manifest)

    with patch("robot_md.init_phases.calibrate_sign.sys.stdin.isatty", return_value=False):
        result = phase_calibrate_sign(manifest)

    assert result.status == "skipped"
    assert result.phase == "sign_cal"


def test_skipped_when_hardware_absent(tmp_path):
    from robot_md.init_phases import phase_calibrate_sign

    manifest = tmp_path / "ROBOT.md"
    _write_feetech_manifest(manifest)

    with (
        patch("robot_md.init_phases.calibrate_sign.sys.stdin.isatty", return_value=True),
        patch("robot_md.init_phases.calibrate_sign._probe_feetech_port", return_value=False),
    ):
        result = phase_calibrate_sign(manifest)

    assert result.status == "skipped"


def test_ok_runs_cli_calibrate_sign(tmp_path):
    from robot_md.init_phases import phase_calibrate_sign

    manifest = tmp_path / "ROBOT.md"
    _write_feetech_manifest(manifest)

    with (
        patch("robot_md.init_phases.calibrate_sign.sys.stdin.isatty", return_value=True),
        patch("robot_md.init_phases.calibrate_sign._probe_feetech_port", return_value=True),
        patch("robot_md.init_phases.calibrate_sign.input", return_value="y"),
        patch("robot_md.init_phases.calibrate_sign.cli_calibrate_sign", return_value=0) as run,
    ):
        result = phase_calibrate_sign(manifest)

    assert result.status == "ok"
    run.assert_called_once_with(str(manifest))


def test_failed_when_cli_returns_nonzero(tmp_path):
    from robot_md.init_phases import phase_calibrate_sign

    manifest = tmp_path / "ROBOT.md"
    _write_feetech_manifest(manifest)

    with (
        patch("robot_md.init_phases.calibrate_sign.sys.stdin.isatty", return_value=True),
        patch("robot_md.init_phases.calibrate_sign._probe_feetech_port", return_value=True),
        patch("robot_md.init_phases.calibrate_sign.input", return_value="y"),
        patch("robot_md.init_phases.calibrate_sign.cli_calibrate_sign", return_value=2),
    ):
        result = phase_calibrate_sign(manifest)

    assert result.status == "failed"
    assert result.detail and result.detail.get("exit_code") == 2
