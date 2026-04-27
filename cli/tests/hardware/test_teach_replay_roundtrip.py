"""Bob hardware smoke: open ServoBus against /dev/ttyACM0, read all 6 servos,
do a tiny ±1-step wiggle on shoulder_pan, verify positions returned to start.

Gated by `--run-hardware`. Skipped otherwise."""

from __future__ import annotations

import os
import time

import pytest

pytestmark = pytest.mark.hardware

pytest.importorskip("scservo_sdk")


class _NoopEstop:
    def is_set(self):
        return False


def _bus():
    from robot_md.backends.feetech_depthai.servo import ServoBus

    return ServoBus(port="/dev/ttyACM0", baud=1_000_000, count=6)


def test_read_all_six_servos():
    if not os.path.exists("/dev/ttyACM0"):
        pytest.skip("no /dev/ttyACM0")
    bus = _bus()
    bus.open()
    try:
        positions = bus.read_positions()
        assert len(positions) == 6, f"expected 6 responders, got {positions}"
    finally:
        bus.close()


def test_shoulder_pan_one_step_wiggle():
    """Nudges shoulder_pan ±1 step. Operator should see no visible motion but
    the bus should accept the writes without error."""
    if not os.path.exists("/dev/ttyACM0"):
        pytest.skip("no /dev/ttyACM0")
    bus = _bus()
    bus.open()
    try:
        start = bus.read_positions()
        assert "shoulder_pan" in start
        sp = start["shoulder_pan"]
        bus.torque(True)
        try:
            target = dict(start)
            target["shoulder_pan"] = sp + 1
            bus.interpolate(start, target, hz=30, max_steps_per_tick=1, estop=_NoopEstop())
            time.sleep(0.1)
            bus.interpolate(target, start, hz=30, max_steps_per_tick=1, estop=_NoopEstop())
            time.sleep(0.1)
        finally:
            bus.torque(False)
        end = bus.read_positions()
        assert abs(end["shoulder_pan"] - sp) <= 2
    finally:
        bus.close()


def test_depthai_frame_capture():
    """Grab one aligned RGB+depth frame from the connected OAK-D."""
    pytest.importorskip("depthai")
    from robot_md.backends.feetech_depthai.perception import Perception
    from robot_md.parser import parse_file
    from robot_md.robot_spec import RobotSpec

    fixtures = os.path.join(os.path.dirname(__file__), "..", "fixtures")
    parsed = parse_file(os.path.join(fixtures, "robot_md_oak_d_factory_cal.yaml"))
    spec = RobotSpec.from_parsed(parsed)

    p = Perception.from_spec(spec)
    try:
        p.open()
    except RuntimeError as e:
        pytest.skip(f"depthai device not available: {e}")
    try:
        rgb, depth, K = p.grab_frame()
        assert rgb is not None and depth is not None
        assert K is not None and K.shape == (3, 3)
    finally:
        p.close()
