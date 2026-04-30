from __future__ import annotations

from dataclasses import fields

from robot_md.hotplug.event import DeviceEvent


def test_all_event_field_names_stable() -> None:
    """If anyone touches DeviceEvent's field set, they must update all three
    watchers + the matcher together. This test pins the field names."""
    expected = {
        "kind", "vid", "pid", "serial", "path",
        "transport", "raw_metadata", "detected_at",
    }
    actual = {f.name for f in fields(DeviceEvent)}
    assert actual == expected, (
        f"DeviceEvent fields drifted from canonical set. "
        f"Expected {expected}, got {actual}. "
        f"Update linux.py / macos.py / windows.py + matcher.py atomically."
    )
