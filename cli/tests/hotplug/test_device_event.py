from __future__ import annotations

import dataclasses

import pytest

from robot_md.hotplug.event import DeviceEvent, classify_transport


def test_device_event_is_frozen() -> None:
    e = DeviceEvent(
        kind="usb_added",
        vid="1a86",
        pid="7523",
        serial="AB12",
        path="/dev/ttyACM0",
        transport="feetech",
        raw_metadata={},
        detected_at="2026-04-27T19:30:11Z",
    )
    with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
        e.path = "/dev/ttyACM1"


def test_classify_transport_known_feetech_chip() -> None:
    # CH340 — bog-standard feetech bus chip used by SO-ARM101.
    assert classify_transport(vid="1a86", pid="7523", subsystem="tty") == "feetech"


def test_classify_transport_realsense() -> None:
    # Intel RealSense D435 vendor ID.
    assert classify_transport(vid="8086", pid="0b07", subsystem="usb") == "realsense"


def test_classify_transport_unknown() -> None:
    assert classify_transport(vid="dead", pid="beef", subsystem="usb") == "unknown"


def test_classify_transport_handles_none_vid_or_pid() -> None:
    """Bare-metal /dev/tty entries sometimes lack VID/PID — must not raise."""
    assert classify_transport(vid=None, pid="7523", subsystem="tty") == "unknown"
    assert classify_transport(vid="1a86", pid=None, subsystem="tty") == "unknown"
    assert classify_transport(vid=None, pid=None, subsystem="tty") == "unknown"


def test_classify_transport_case_insensitive_vid_pid() -> None:
    """VID/PID strings come back uppercase from some watchers, lowercase from others."""
    assert classify_transport(vid="1A86", pid="7523", subsystem="tty") == "feetech"
    assert classify_transport(vid="1a86", pid="7523", subsystem="tty") == "feetech"
