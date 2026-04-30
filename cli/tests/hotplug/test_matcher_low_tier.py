from __future__ import annotations

from unittest.mock import patch

from robot_md.hotplug.event import DeviceEvent
from robot_md.hotplug.matcher import classify


def _evt(transport="unknown", vid="dead", pid="beef") -> DeviceEvent:
    return DeviceEvent(
        kind="usb_added",
        vid=vid,
        pid=pid,
        serial=None,
        path="/dev/ttyACM0",
        transport=transport,
        raw_metadata={},
        detected_at="2026-04-27T19:30:11Z",
    )


def test_low_tier_when_unknown_vid_pid() -> None:
    decision = classify(_evt())
    assert decision.tier == "LOW"
    assert any("preset" in r.lower() for r in decision.reasons)


def test_low_tier_when_known_transport_no_backend() -> None:
    with patch("robot_md.hotplug.matcher._installed_backends_for_transport", return_value=[]):
        decision = classify(_evt(transport="feetech", vid="1a86", pid="7523"))
    assert decision.tier == "LOW"
    assert any("backend" in r.lower() for r in decision.reasons)
