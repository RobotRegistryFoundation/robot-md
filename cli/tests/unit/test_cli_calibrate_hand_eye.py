"""CLI surface: `robot-md calibrate --extrinsic` is the primary flag;
`--hand-eye` is a deprecation alias that emits a warning and runs the
new code path."""
from __future__ import annotations

from unittest.mock import patch

from typer.testing import CliRunner

from robot_md.__main__ import app


def _phase_stub(status="skipped", reason="no_actuatable_bus"):
    return type("PR", (), {
        "status": status,
        "message": f"stubbed {status}",
        "detail": {"reason": reason},
    })()


def test_calibrate_extrinsic_flag_invokes_phase(tmp_path):
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("---\nmetadata: {robot_name: bob}\n---\n# bob\n")
    runner = CliRunner()
    with patch("robot_md.__main__.phase_calibrate_extrinsic", return_value=_phase_stub()) as p:
        result = runner.invoke(app, ["calibrate", "--extrinsic", str(manifest)])
    assert result.exit_code == 0, result.output
    p.assert_called_once()


def test_calibrate_hand_eye_flag_is_deprecated_alias(tmp_path):
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("---\nmetadata: {robot_name: bob}\n---\n# bob\n")
    runner = CliRunner()
    with patch("robot_md.__main__.phase_calibrate_extrinsic", return_value=_phase_stub()) as p:
        result = runner.invoke(app, ["calibrate", "--hand-eye", str(manifest)])
    assert result.exit_code == 0, result.output
    # Deprecation warning should be surfaced — check stdout + stderr.
    combined = (result.output or "") + (getattr(result, "stderr_bytes", b"").decode() if getattr(result, "stderr_bytes", None) else "")
    assert "deprecated" in combined.lower()
    p.assert_called_once()
