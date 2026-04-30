from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from robot_md.hotplug.event import DeviceEvent
from robot_md.hotplug.matcher import classify
from robot_md.hotplug.presets_index import PresetMatch


def _evt(serial="AB12") -> DeviceEvent:
    return DeviceEvent(
        kind="tty_added", vid="1a86", pid="7523", serial=serial,
        path="/dev/ttyACM0", transport="feetech",
        raw_metadata={}, detected_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )


def test_recent_reject_within_window_demotes_high_to_medium(monkeypatch) -> None:
    monkeypatch.setattr(
        "robot_md.hotplug.presets_index.lookup_by_vid_pid",
        lambda *, vid, pid: [PresetMatch("so_arm101", "feetech", "exact_match")],
    )
    recent = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat().replace("+00:00", "Z")
    with patch("robot_md.hotplug.matcher._installed_backends_for_transport", return_value=["lerobot"]), \
         patch("robot_md.hotplug.matcher._recent_reject_for", return_value=recent):
        decision = classify(_evt())
    assert decision.tier == "MEDIUM"
    assert any("rejected" in r.lower() for r in decision.reasons)


def test_old_reject_does_not_demote(monkeypatch) -> None:
    monkeypatch.setattr(
        "robot_md.hotplug.presets_index.lookup_by_vid_pid",
        lambda *, vid, pid: [PresetMatch("so_arm101", "feetech", "exact_match")],
    )
    old = (datetime.now(timezone.utc) - timedelta(hours=4)).isoformat().replace("+00:00", "Z")
    with patch("robot_md.hotplug.matcher._installed_backends_for_transport", return_value=["lerobot"]), \
         patch("robot_md.hotplug.matcher._recent_reject_for", return_value=old):
        decision = classify(_evt())
    assert decision.tier == "HIGH"
