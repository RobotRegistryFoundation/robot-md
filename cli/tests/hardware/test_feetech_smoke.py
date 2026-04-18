"""Hardware smoke: nudge servo ID 1 by ±1 step. Requires a real STS3215 bus."""

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
    try:
        # Smoke: send +1 then -1 around the reference zero for shoulder_pan.
        # Real STS3215 write-register protocol is filled in by follow-up work;
        # the current ServoBus.write_positions is a no-op, so this smoke test
        # documents the hardware contract rather than asserting motion.
        bus.write_positions({"shoulder_pan": 2049})
        bus.write_positions({"shoulder_pan": 2048})
    finally:
        bus.close()
