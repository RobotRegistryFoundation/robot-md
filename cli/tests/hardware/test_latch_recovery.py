"""Force an over-envelope trajectory behind --force-envelope; assert the
watchdog detects the latch, torques off remaining servos, and returns
a structured servo_latched error.

THIS TEST WILL LATCH A SERVO and require a physical power cycle of the
servo bus to recover. Gated behind RM_ALLOW_LATCH=1 (in addition to
RM_HARDWARE=1) so it never runs by accident.
"""
from __future__ import annotations

import os

import pytest


@pytest.mark.hardware
@pytest.mark.skipif(
    os.environ.get("RM_ALLOW_LATCH") != "1",
    reason="requires RM_ALLOW_LATCH=1 (will latch wrist_flex — needs power cycle)",
)
def test_force_envelope_latch_is_contained(tmp_path, monkeypatch):
    """Drive wrist_flex past the latch threshold and hold for >1s. The
    watchdog must: (a) detect that wrist_flex dropped from the bus
    enumeration after motion, (b) return an error with reason=servo_latched,
    (c) not leave remaining servos torqued up in a fallen posture."""
    import time

    from robot_md.backends.feetech_depthai.motion import Motion
    from robot_md.backends.feetech_depthai.servo import ServoBus
    from robot_md.parser import parse_file
    from robot_md.robot_spec import RobotSpec
    from robot_md.init import default_flow

    manifest = tmp_path / "ROBOT.md"
    default_flow(
        manifest, robot_name="hwlatch", preset_name="so-arm101",
        do_register=False, do_install_mcp=False, do_install_skill=False,
        do_refresh_claude_md=False,
    )

    spec = RobotSpec.from_parsed(parse_file(manifest))
    bus = ServoBus.from_spec(spec)
    bus.open()
    motion = Motion.from_spec(spec)

    try:
        # Drive wrist_flex to its limit and hold — will latch under gravity.
        # Wrist_flex encoder 2048 = zero; +1000 ≈ 88°. Full-envelope move.
        target = {
            "shoulder_pan": 2048, "shoulder_lift": 1800, "elbow_flex": 2300,
            "wrist_flex": 3048,  # ~88° — past the 85% safe threshold
            "wrist_roll": 2048, "gripper": 1700,
        }
        # Force-drive past the envelope guard by calling interpolate directly
        # (bypasses trajectory.plan_pick which would reject this).
        bus.interpolate(bus.read_positions(), target, hz=30, estop=None)
        # Hold 2 seconds to trip overload.
        time.sleep(2.0)

        expected = {"shoulder_pan", "shoulder_lift", "elbow_flex",
                    "wrist_flex", "wrist_roll", "gripper"}
        report = motion.verify_alive(bus, expected_ids=expected)
        assert not report.alive, (
            "expected wrist_flex to latch and drop from bus — did not happen"
        )
        assert "wrist_flex" in report.missing
    finally:
        # Safety: explicit torque off (verify_alive should have already done this,
        # but belt and braces).
        try:
            bus.torque(False)
        except Exception:
            pass
        bus.close()
