"""Unit tests for phase_write_manifest — extracted from init.quick."""
from __future__ import annotations


class _Device:
    def __init__(self, bus=None, protocol=None, label="", path=None):
        self.bus = bus
        self.protocol = protocol
        self.label = label
        self.path = path


class _Scan:
    def __init__(self, devices):
        self.devices = devices
        self.cameras: list = []


def _fake_so_arm101_scan():
    return _Scan(
        [
            _Device(bus="usb", protocol="feetech", label="Feetech servo bus", path="/dev/ttyACM0"),
        ]
    )


def test_writes_manifest_with_explicit_preset(tmp_path):
    from robot_md.init_phases import phase_write_manifest

    out = tmp_path / "ROBOT.md"
    result = phase_write_manifest(
        out_path=out,
        robot_name="bob",
        preset_name="so-arm101",
        scan=_fake_so_arm101_scan(),
        force=False,
    )

    assert result.status == "ok"
    assert out.exists()
    text = out.read_text()
    assert "bob" in text
    assert "so-arm101" in text or "so_arm101" in text


def test_refuses_existing_file_without_force(tmp_path):
    from robot_md.init_phases import phase_write_manifest

    out = tmp_path / "ROBOT.md"
    out.write_text("old\n")

    result = phase_write_manifest(
        out_path=out,
        robot_name="bob",
        preset_name="so-arm101",
        scan=_fake_so_arm101_scan(),
        force=False,
    )

    assert result.status == "failed"
    assert "exist" in result.message.lower()


def test_overwrites_with_force(tmp_path):
    from robot_md.init_phases import phase_write_manifest

    out = tmp_path / "ROBOT.md"
    out.write_text("old\n")

    result = phase_write_manifest(
        out_path=out,
        robot_name="bob",
        preset_name="so-arm101",
        scan=_fake_so_arm101_scan(),
        force=True,
    )

    assert result.status == "ok"
    assert "old" not in out.read_text()


def test_unknown_preset_returns_failed(tmp_path):
    from robot_md.init_phases import phase_write_manifest

    out = tmp_path / "ROBOT.md"
    result = phase_write_manifest(
        out_path=out,
        robot_name="bob",
        preset_name="nonexistent-preset",
        scan=_fake_so_arm101_scan(),
        force=False,
    )

    assert result.status == "failed"
    assert "not found" in result.message.lower() or "nonexistent" in result.message
    assert not out.exists()
