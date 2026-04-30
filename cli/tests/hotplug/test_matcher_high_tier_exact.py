from __future__ import annotations

from unittest.mock import patch

from robot_md.hotplug.event import DeviceEvent
from robot_md.hotplug.matcher import classify
from robot_md.hotplug.presets_index import PresetMatch


def _evt() -> DeviceEvent:
    return DeviceEvent(
        kind="tty_added",
        vid="1a86", pid="7523", serial="UNIQUE_SERIAL_AB12",
        path="/dev/ttyACM0",
        transport="feetech",
        raw_metadata={},
        detected_at="2026-04-27T19:30:11Z",
    )


def test_high_tier_when_serial_uniquely_identifies_preset_and_one_backend(monkeypatch) -> None:
    # Single-preset match (override the table to simulate a serial-unique preset).
    monkeypatch.setattr(
        "robot_md.hotplug.presets_index.lookup_by_vid_pid",
        lambda *, vid, pid: [PresetMatch("so_arm101", "feetech", "exact_match")],
    )
    # Only lerobot backend installed.
    with patch("robot_md.hotplug.matcher._installed_backends_for_transport",
               return_value=["lerobot"]):
        decision = classify(_evt())
    assert decision.tier == "HIGH"
    assert decision.unambiguous is True
    assert decision.bind_proposal is not None
    assert decision.bind_proposal.backend_name == "lerobot"
    assert decision.bind_proposal.preset_name == "so_arm101"
