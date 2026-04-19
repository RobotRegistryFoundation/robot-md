from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

from robot_md.backends.feetech_depthai import FeetechDepthaiBackend
from robot_md.parser import parse_file
from robot_md.robot_spec import RobotSpec


def _install_fake_feetech(monkeypatch):
    fake = MagicMock()
    fp = MagicMock()
    fp.openPort.return_value = True
    fp.setBaudRate.return_value = True
    fake.PortHandler.return_value = fp
    ph = MagicMock()
    ph.read2ByteTxRx.return_value = (2048, 0, 0)
    fake.PacketHandler.return_value = ph
    monkeypatch.setitem(sys.modules, "feetech_servo_sdk", fake)
    monkeypatch.setitem(sys.modules, "depthai", None)


def test_refuses_open_without_max_joint_velocity(fixtures_dir):
    """Backend open() raises RuntimeError when safety.max_joint_velocity_dps is missing."""
    parsed = parse_file(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    # Remove the max_joint_velocity_dps field that fixture now has
    if "max_joint_velocity_dps" in parsed.frontmatter["safety"]:
        del parsed.frontmatter["safety"]["max_joint_velocity_dps"]
    spec = RobotSpec.from_parsed(parsed)
    # spec now has no max_joint_velocity_dps
    assert spec.safety.max_joint_velocity_dps is None
    with pytest.raises(RuntimeError, match="max_joint_velocity_dps"):
        FeetechDepthaiBackend().open(spec)


def test_opens_with_max_joint_velocity(fixtures_dir, monkeypatch):
    _install_fake_feetech(monkeypatch)
    parsed = parse_file(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    parsed.frontmatter["safety"]["max_joint_velocity_dps"] = 180
    spec = RobotSpec.from_parsed(parsed)
    backend = FeetechDepthaiBackend()
    backend.open(spec)
    assert backend.capabilities() >= {"arm.pick", "arm.place"}
    backend.close()


def test_scene_describe_returns_snapshot_after_open(fixtures_dir, monkeypatch):
    _install_fake_feetech(monkeypatch)
    parsed = parse_file(fixtures_dir / "robot_md_oak_d_factory_cal.yaml")
    parsed.frontmatter["safety"]["max_joint_velocity_dps"] = 180
    spec = RobotSpec.from_parsed(parsed)
    backend = FeetechDepthaiBackend()
    backend.open(spec)
    try:
        snap = backend.scene_describe()
        assert snap is not None
        # Perception init fails (depthai mocked to None) so frame should be None.
        assert snap.detections == ()
        assert snap.frame is None
        assert snap.ts > 0
    finally:
        backend.close()


def test_scene_describe_before_open_returns_empty(fixtures_dir):
    """scene_describe() on a freshly-constructed backend (not opened) returns an empty snapshot."""
    backend = FeetechDepthaiBackend()
    snap = backend.scene_describe()
    # Before open, _perception and _servo_bus are None — scene_describe should
    # gracefully return an empty snapshot, NOT raise.
    assert snap.frame is None
    assert snap.detections == ()
    assert snap.joint_state == {}
