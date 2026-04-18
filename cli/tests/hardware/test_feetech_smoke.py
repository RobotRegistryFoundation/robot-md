"""Hardware smoke: superseded by `test_teach_replay_roundtrip.py`.

This file existed as a placeholder in v0.3.0 before `ServoBus.write_positions`
did any real I/O. The v0.4.0 real implementation now requires `open()` first
and would raise without it. Keep the test but delegate to the richer
roundtrip smoke that replaces it.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.hardware

pytest.importorskip("serial")


def test_single_servo_nudge():
    if not os.path.exists("/dev/ttyACM0"):
        pytest.skip("no /dev/ttyACM0")
    from robot_md.backends.feetech_depthai.servo import ServoBus

    bus = ServoBus(port="/dev/ttyACM0", baud=1_000_000, count=6)
    bus.open()
    try:
        bus.torque(True)
        try:
            bus.write_positions({"shoulder_pan": 2049})
            bus.write_positions({"shoulder_pan": 2048})
        finally:
            bus.torque(False)
    finally:
        bus.close()
