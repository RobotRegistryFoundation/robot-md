"""`robot-md doctor --hardware=on` with a synthetic bus missing a servo
surfaces a warn (not pass). End-to-end through the typer CLI."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from robot_md.__main__ import app
from robot_md.init_phases import PhaseResult


def _stub_phase(name):
    def _inner(*a, **kw):
        return PhaseResult(phase=name, status="skipped", message="", detail={})
    return _inner


@pytest.mark.integration
def test_doctor_warns_on_servo_missing(tmp_path):
    """Synthetic bus missing wrist_flex → doctor emits a warn row."""
    # Build a manifest from the so-arm101 preset (has full kinematics block
    # with all 6 joints including wrist_flex).
    from robot_md.init import default_flow

    manifest = tmp_path / "ROBOT.md"

    with (
        patch("robot_md.init.phase_register", _stub_phase("register")),
        patch("robot_md.init.phase_install_mcp", _stub_phase("install_mcp")),
        patch("robot_md.init.phase_install_skill", _stub_phase("install_skill")),
        patch("robot_md.init.phase_calibrate_sign", _stub_phase("calibrate_sign")),
        patch("robot_md.init.phase_calibrate_zero", _stub_phase("calibrate_zero")),
        patch("robot_md.init.phase_calibrate_extrinsic", _stub_phase("calibrate_extrinsic")),
        patch("robot_md.init.phase_teach_poses", _stub_phase("teach_poses")),
        patch("robot_md.init._refresh_claude_md"),
    ):
        rc = default_flow(
            manifest,
            robot_name="doctortest",
            preset_name="so-arm101",
            do_register=False,
            do_install_mcp=False,
            do_install_skill=False,
            do_refresh_claude_md=False,
        )
    assert rc == 0, f"default_flow failed rc={rc}"
    assert manifest.exists(), "manifest was not written"

    # Synthetic bus: wrist_flex dropped — simulates a latched servo.
    bus = MagicMock()
    bus.read_positions.return_value = {
        "shoulder_pan": 2048,
        "shoulder_lift": 2048,
        "elbow_flex": 2048,
        # wrist_flex omitted
        "wrist_roll": 2048,
        "gripper": 1700,
    }
    bus.open.return_value = None
    bus.close.return_value = None

    camera = MagicMock()
    camera.probe.return_value = {"rgb": True, "depth": True}

    with (
        patch(
            "robot_md.backends.feetech_depthai.servo.ServoBus.from_spec",
            return_value=bus,
        ),
        patch(
            "robot_md.backends.feetech_depthai.perception.Perception.from_spec",
            return_value=camera,
        ),
    ):
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["doctor", "--path", str(manifest), "--hardware", "on"],
        )

    # Collect all output — typer may split across stdout / stderr.
    out = result.stdout or ""
    if hasattr(result, "stderr_bytes") and result.stderr_bytes:
        out += result.stderr_bytes.decode(errors="replace")

    lower = out.lower()

    # The warn must mention either the missing servo name OR the check name.
    assert "wrist_flex" in lower or "servo_enumeration" in lower, (
        f"expected hardware warn in output — exit={result.exit_code}\n"
        f"stdout+stderr:\n{out}"
    )
    assert "warn" in lower or "missing" in lower or "latch" in lower, (
        f"expected warn/missing/latch language — exit={result.exit_code}\n"
        f"stdout+stderr:\n{out}"
    )
