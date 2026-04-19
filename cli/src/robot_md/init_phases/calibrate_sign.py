"""Phase: encoder-sign calibration — wraps cli_calibrate_sign with pre-flight."""

from __future__ import annotations

import sys
from pathlib import Path

from robot_md.calibrate import cli_calibrate_sign
from robot_md.init_phases import PhaseResult
from robot_md.init_phases.calibrate_zero import _drivers, _probe_feetech_port


def phase_calibrate_sign(manifest_path: Path, *, prompt: bool = True) -> PhaseResult:
    """Run encoder-sign calibration if TTY + hardware are present.

    Same pre-flight as phase_calibrate_zero: stdin TTY + feetech port
    probe. Delegates to robot_md.calibrate.cli_calibrate_sign which
    wiggles each joint and asks the operator which direction it moved.
    """
    if not sys.stdin.isatty():
        return PhaseResult(
            phase="sign_cal",
            status="skipped",
            message="no TTY; run `robot-md calibrate --sign ROBOT.md` separately",
            detail={"reason": "no_tty"},
        )

    drivers = _drivers(manifest_path)
    if not drivers or drivers[0].get("protocol") != "feetech":
        return PhaseResult(
            phase="sign_cal",
            status="skipped",
            message="no feetech driver declared; sign calibration is a no-op",
            detail={"reason": "no_feetech_driver"},
        )

    port = drivers[0].get("port") or "/dev/ttyACM0"
    baud = int(drivers[0].get("baud_rate") or drivers[0].get("baud") or 1_000_000)

    if not _probe_feetech_port(port, baud):
        return PhaseResult(
            phase="sign_cal",
            status="skipped",
            message=f"no hardware detected on {port}; run `robot-md calibrate --sign ROBOT.md` "
            f"after plugging in the arm",
            detail={"reason": "no_hardware", "port": port},
        )

    if prompt:
        try:
            answer = input("Run encoder-sign calibration now? [Y/n] > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return PhaseResult(
                phase="sign_cal",
                status="skipped",
                message="operator aborted",
                detail={"reason": "aborted"},
            )
        if answer.startswith("n"):
            return PhaseResult(
                phase="sign_cal",
                status="skipped",
                message="operator declined",
                detail={"reason": "declined"},
            )

    rc = cli_calibrate_sign(str(manifest_path))
    if rc == 0:
        return PhaseResult(
            phase="sign_cal",
            status="ok",
            message="encoder_sign patched",
            detail={"exit_code": 0},
        )
    return PhaseResult(
        phase="sign_cal",
        status="failed",
        message=f"cli_calibrate_sign exit code {rc}",
        detail={"exit_code": rc},
    )
