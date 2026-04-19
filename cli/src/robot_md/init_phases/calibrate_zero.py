"""Phase: zero-pose calibration — wraps cli_calibrate_zero with pre-flight."""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

from robot_md.calibrate import cli_calibrate_zero
from robot_md.init_phases import PhaseResult
from robot_md.parser import parse_file


def _probe_feetech_port(port: str, baud: int = 1_000_000) -> bool:
    """Return True if the port opens and servo id 1 responds to Present Position.

    Runs in a few hundred ms; imports feetech_servo_sdk lazily so the
    phase module is importable on systems without the hardware SDK.
    """
    try:
        from feetech_servo_sdk import PacketHandler, PortHandler  # lazy
    except Exception:
        return False
    ph = PortHandler(port)
    try:
        if not ph.openPort():
            return False
        if not ph.setBaudRate(baud):
            return False
        pk = PacketHandler(0)
        _, comm, err = pk.read2ByteTxRx(ph, 1, 56)  # servo id 1, ADDR_PRESENT
        return comm == 0 and err == 0
    except Exception:
        return False
    finally:
        with contextlib.suppress(Exception):
            ph.closePort()


def _drivers(manifest_path: Path) -> list[dict]:
    try:
        parsed = parse_file(manifest_path)
    except Exception:
        return []
    return list(parsed.frontmatter.get("drivers") or [])


def phase_calibrate_zero(manifest_path: Path, *, prompt: bool = True) -> PhaseResult:
    """Run zero-pose calibration if TTY + hardware are present.

    Pre-flight:
      1. stdin.isatty() — skip if not a TTY.
      2. _probe_feetech_port — skip if the declared feetech port does not
         respond to a single servo read.
    If `prompt=True`, asks the operator Y/n before running.
    """
    if not sys.stdin.isatty():
        return PhaseResult(
            phase="zero_cal",
            status="skipped",
            message="no TTY; run `robot-md calibrate --zero ROBOT.md` separately",
            detail={"reason": "no_tty"},
        )

    drivers = _drivers(manifest_path)
    if not drivers or drivers[0].get("protocol") != "feetech":
        return PhaseResult(
            phase="zero_cal",
            status="skipped",
            message="no feetech driver declared; zero calibration is a no-op",
            detail={"reason": "no_feetech_driver"},
        )

    port = drivers[0].get("port") or "/dev/ttyACM0"
    baud = int(drivers[0].get("baud_rate") or drivers[0].get("baud") or 1_000_000)

    if not _probe_feetech_port(port, baud):
        return PhaseResult(
            phase="zero_cal",
            status="skipped",
            message=f"no hardware detected on {port}; run `robot-md calibrate --zero ROBOT.md` "
            f"after plugging in the arm",
            detail={"reason": "no_hardware", "port": port},
        )

    if prompt:
        try:
            answer = input("Run zero-pose calibration now? [Y/n] > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return PhaseResult(
                phase="zero_cal",
                status="skipped",
                message="operator aborted",
                detail={"reason": "aborted"},
            )
        if answer.startswith("n"):
            return PhaseResult(
                phase="zero_cal",
                status="skipped",
                message="operator declined",
                detail={"reason": "declined"},
            )

    rc = cli_calibrate_zero(str(manifest_path))
    if rc == 0:
        return PhaseResult(
            phase="zero_cal",
            status="ok",
            message="zero_pose_steps patched",
            detail={"exit_code": 0},
        )
    return PhaseResult(
        phase="zero_cal",
        status="failed",
        message=f"cli_calibrate_zero exit code {rc}",
        detail={"exit_code": rc},
    )
