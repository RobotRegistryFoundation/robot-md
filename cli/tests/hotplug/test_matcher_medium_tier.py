from __future__ import annotations

from unittest.mock import patch

from robot_md.hotplug.event import DeviceEvent
from robot_md.hotplug.matcher import classify


def _evt() -> DeviceEvent:
    return DeviceEvent(
        kind="tty_added", vid="1a86", pid="7523", serial=None,
        path="/dev/ttyACM0", transport="feetech",
        raw_metadata={}, detected_at="2026-04-27T19:30:11Z",
    )


def test_medium_tier_when_multi_preset_match() -> None:
    # Default presets-index returns 3 matches for 1a86:7523.
    with patch("robot_md.hotplug.matcher._installed_backends_for_transport",
               return_value=["lerobot"]):
        decision = classify(_evt())
    assert decision.tier == "MEDIUM"
    assert decision.unambiguous is False
    assert len(decision.alternatives) >= 2
