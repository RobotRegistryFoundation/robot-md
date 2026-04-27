"""Shared pre-flight helpers for the feetech-based calibration phases.

Both `phase_calibrate_zero` and `phase_calibrate_sign` apply the same
gate chain before prompting the operator: confirm a feetech driver is
declared, then confirm the declared port responds to a single-servo
read. Hoisted here so the two phases can't drift on probe semantics.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

from robot_md.parser import parse_file


def probe_feetech_port(port: str, baud: int = 1_000_000) -> bool:
    """Return True if the port opens and servo id 1 responds to Present Position.

    Runs in a few hundred ms; imports `scservo_sdk` lazily so the caller stays
    importable on systems without the hardware SDK. (PyPI dist
    `feetech-servo-sdk` ships the `scservo_sdk` Python module.)
    """
    try:
        from scservo_sdk import PortHandler  # lazy
        from scservo_sdk.sms_sts import sms_sts
    except Exception:
        return False
    try:
        ph = PortHandler(port)
    except Exception:
        return False
    try:
        if not ph.openPort():
            return False
        if not ph.setBaudRate(baud):
            return False
        pk = sms_sts(ph)
        _, comm, err = pk.read2ByteTxRx(1, 56)  # servo id 1, ADDR_PRESENT
        return comm == 0 and err == 0
    except Exception:
        return False
    finally:
        with contextlib.suppress(Exception):
            ph.closePort()


def drivers_from(manifest_path: Path) -> list[dict]:
    """Parse the manifest and return its `drivers[]` frontmatter list.

    Swallows parse errors — the caller decides what "no drivers" means.
    """
    try:
        parsed = parse_file(manifest_path)
    except Exception:
        return []
    return list(parsed.frontmatter.get("drivers") or [])
