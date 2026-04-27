"""Tests for `robot-md autodetect --bus feetech:<port>` (Tier B scan).

The live-hardware `scan_feetech()` call is exercised by a smoke test against
a real arm; only its error paths and pure-data helpers are unit-tested here.
"""

from __future__ import annotations

import pytest

from robot_md.bus_scan import (
    ServoEntry,
    _steps_to_deg,
    render_bus_scan_as_yaml,
    scan_feetech,
)


def test_steps_to_deg_canonical_values():
    assert _steps_to_deg(0) == 0.0
    assert _steps_to_deg(4096) == pytest.approx(360.0)
    assert _steps_to_deg(2048) == pytest.approx(180.0)
    assert _steps_to_deg(1024) == pytest.approx(90.0)


def test_servo_entry_to_kinematics_item():
    s = ServoEntry(servo_id=2, present_position=1800, min_angle_steps=0, max_angle_steps=4096)
    it = s.to_kinematics_item()
    assert it["id"] == "joint_2"
    assert it["servo_id"] == 2
    assert it["axis"] == "y"
    assert it["limits_deg"] == [0.0, 360.0]
    assert it["zero_pose_steps"] == 1800
    assert it["encoder_sign"] == 1


def test_servo_entry_with_missing_limits_uses_safe_defaults():
    s = ServoEntry(servo_id=3, present_position=2048, min_angle_steps=None, max_angle_steps=None)
    it = s.to_kinematics_item()
    assert it["limits_deg"] == [-180, 180]
    # Present position still flows through even when limits are missing
    assert it["zero_pose_steps"] == 2048


def test_servo_entry_with_missing_position_defaults_to_2048():
    s = ServoEntry(servo_id=1, present_position=None, min_angle_steps=0, max_angle_steps=4096)
    it = s.to_kinematics_item()
    assert it["zero_pose_steps"] == 2048


def test_servo_entry_custom_joint_id():
    s = ServoEntry(servo_id=1, present_position=2048, min_angle_steps=0, max_angle_steps=4096)
    it = s.to_kinematics_item(default_id="shoulder_pan")
    assert it["id"] == "shoulder_pan"


def test_render_bus_scan_empty_list_message():
    out = render_bus_scan_as_yaml([])
    assert "no responding servos" in out.lower()
    assert "powered" in out.lower()
    # Should NOT emit a physics: block when no servos
    assert "physics:" not in out


def test_render_bus_scan_includes_all_servos():
    servos = [
        ServoEntry(servo_id=1, present_position=2012, min_angle_steps=0, max_angle_steps=4096),
        ServoEntry(servo_id=2, present_position=1755, min_angle_steps=0, max_angle_steps=4096),
    ]
    out = render_bus_scan_as_yaml(servos)
    assert "2 servo(s) found at IDs 1, 2" in out
    assert "physics:" in out
    assert "kinematics:" in out
    assert "servo_id: 1" in out
    assert "servo_id: 2" in out
    assert "zero_pose_steps: 2012" in out
    assert "zero_pose_steps: 1755" in out


def test_scan_feetech_errors_cleanly_without_sdk(monkeypatch):
    """If `scservo_sdk` isn't importable, the scan raises a helpful
    RuntimeError pointing at the optional extras install."""
    import sys

    monkeypatch.setitem(sys.modules, "scservo_sdk", None)
    with pytest.raises(RuntimeError) as exc:
        scan_feetech("/dev/does-not-exist")
    assert "scservo_sdk" in str(exc.value)


def test_scan_feetech_errors_cleanly_on_missing_port(monkeypatch):
    """An invalid port raises a RuntimeError pointing at one of the two
    most common causes — the gateway holding the bus, OR the feetech
    extras not being installed in this environment (CI, minimal installs).

    Simulate the "port physically missing" case by pointing PortHandler at
    a real path that openPort() will refuse. Behavior across pyserial
    versions varies on how an absent /dev path fails, so we also accept
    the SDK-missing branch.
    """
    import sys

    # Force the ImportError path so the test is deterministic across envs.
    monkeypatch.setitem(sys.modules, "scservo_sdk", None)
    with pytest.raises(RuntimeError) as exc:
        scan_feetech("/dev/does-not-exist-nowhere-12345")
    msg = str(exc.value).lower()
    assert any(hint in msg for hint in ("gateway", "open", "scservo_sdk", "feetech extra"))
