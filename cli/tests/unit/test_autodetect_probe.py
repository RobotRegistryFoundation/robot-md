"""Unit tests for the serial-bus probe step in autodetect.

The problem: lspci / lsusb / /dev/tty* enumeration can tell us "there is a
CH340 USB-serial chip" but not "the thing on the other side is a Feetech
servo bus." Preset matching keys on `drivers.protocol=feetech`, so a
CH340 that's actually driving an SO-ARM101 scores zero against
`so_arm101.yaml` — every preset ties at 0 and alphabetical fallback picks
`aloha2`.

`_probe_servo_buses` walks any /dev/ttyACM* or /dev/ttyUSB* device in the
scan, calls `bus_scan.scan_feetech` on it, and if servos respond,
appends a synthetic Device(protocol='feetech') so the preset matcher
can score so-arm101 correctly.
"""

from __future__ import annotations

from unittest.mock import patch

from robot_md.autodetect import Device, _probe_servo_buses


def _tty(path: str) -> Device:
    return Device(
        role="serial-bus",
        driver_id="serial-tty",
        protocol="serial",
        label=f"serial port {path}",
        bus="tty",
        path=path,
    )


def test_no_ttys_means_no_probe():
    # No /dev/ttyACM* or /dev/ttyUSB* devices → never imports bus_scan,
    # never calls scan_feetech, returns empty list.
    with patch("robot_md.bus_scan.scan_feetech") as sf:
        result = _probe_servo_buses([])
    assert result == []
    sf.assert_not_called()


def test_servo_bus_promotes_tty_to_feetech_device():
    devices = [_tty("/dev/ttyACM0")]
    # Fake a 6-servo SO-ARM101 response.
    fake_servos = [object()] * 6
    with patch("robot_md.bus_scan.scan_feetech", return_value=fake_servos):
        result = _probe_servo_buses(devices)
    assert len(result) == 1
    assert result[0].protocol == "feetech"
    assert result[0].path == "/dev/ttyACM0"
    assert "6" in result[0].label  # servo count surfaces


def test_empty_probe_means_no_promotion():
    # Probe succeeds but finds no servos → do not claim it's feetech.
    devices = [_tty("/dev/ttyACM0")]
    with patch("robot_md.bus_scan.scan_feetech", return_value=[]):
        result = _probe_servo_buses(devices)
    assert result == []


def test_probe_exception_does_not_crash():
    devices = [_tty("/dev/ttyACM0")]
    with patch("robot_md.bus_scan.scan_feetech", side_effect=RuntimeError("port busy")):
        result = _probe_servo_buses(devices)
    assert result == []


def test_permission_error_surfaces_to_warnings(capsys):
    """PermissionError on /dev/ttyACM* must NOT be silently swallowed.
    Caught on Bob during Spec B Phase E T22 cold install; tracked at #82."""
    devices = [_tty("/dev/ttyACM0")]
    warnings: list[str] = []
    with patch(
        "robot_md.bus_scan.scan_feetech",
        side_effect=PermissionError(13, "Permission denied", "/dev/ttyACM0"),
    ):
        result = _probe_servo_buses(devices, warnings=warnings)

    assert result == []
    assert len(warnings) == 1
    assert "/dev/ttyACM0" in warnings[0]
    assert "robot-md-gateway" in warnings[0]
    assert "usermod" in warnings[0]
    captured = capsys.readouterr()
    assert "/dev/ttyACM0" in captured.err
    assert "usermod" in captured.err


def test_permission_error_without_warnings_list_still_prints(capsys):
    """Backward compat: legacy callers without a warnings list still get
    the stderr remediation hint so the message cannot be lost."""
    devices = [_tty("/dev/ttyACM0")]
    with patch(
        "robot_md.bus_scan.scan_feetech",
        side_effect=PermissionError(13, "Permission denied", "/dev/ttyACM0"),
    ):
        result = _probe_servo_buses(devices)
    assert result == []
    captured = capsys.readouterr()
    assert "/dev/ttyACM0" in captured.err


def test_generic_exception_still_silent(capsys):
    """Non-PermissionError exceptions remain silent — not operator-actionable."""
    devices = [_tty("/dev/ttyACM0")]
    warnings: list[str] = []
    with patch(
        "robot_md.bus_scan.scan_feetech",
        side_effect=RuntimeError("scservo_sdk not installed"),
    ):
        result = _probe_servo_buses(devices, warnings=warnings)
    assert result == []
    assert warnings == []
    captured = capsys.readouterr()
    assert captured.err == ""


def test_env_var_skip_disables_probe():
    devices = [_tty("/dev/ttyACM0")]
    with (
        patch.dict("os.environ", {"ROBOT_MD_SKIP_BUS_PROBE": "1"}),
        patch("robot_md.bus_scan.scan_feetech") as sf,
    ):
        result = _probe_servo_buses(devices)
    assert result == []
    sf.assert_not_called()


def test_only_acm_and_usb_paths_probed():
    # /dev/ttyS0 is a built-in UART (often a console). We must NOT send
    # Feetech packets to it. Only /dev/ttyACM* and /dev/ttyUSB* qualify.
    devices = [_tty("/dev/ttyS0"), _tty("/dev/ttyACM0"), _tty("/dev/ttyUSB1")]
    call_paths: list[str] = []

    def _record(port, *_, **__):
        call_paths.append(port)
        return []

    with patch("robot_md.bus_scan.scan_feetech", side_effect=_record):
        _probe_servo_buses(devices)

    assert call_paths == ["/dev/ttyACM0", "/dev/ttyUSB1"]


def test_missing_feetech_sdk_silently_skips():
    # If scservo_sdk isn't installed, bus_scan's scan_feetech raises
    # ImportError on call (per its own docstring). Probe must still
    # degrade to "no promotion" rather than crashing.
    devices = [_tty("/dev/ttyACM0")]
    with patch("robot_md.bus_scan.scan_feetech", side_effect=ImportError("no sdk")):
        result = _probe_servo_buses(devices)
    assert result == []
