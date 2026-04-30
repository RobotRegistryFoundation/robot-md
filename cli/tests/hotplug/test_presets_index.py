from __future__ import annotations

from robot_md.hotplug.presets_index import lookup_by_vid_pid


def test_lookup_so_arm101_by_known_vid_pid() -> None:
    matches = lookup_by_vid_pid(vid="1a86", pid="7523")
    names = {m.preset_name for m in matches}
    # All SO-ARM presets share the CH340 chip; they all match.
    assert "so_arm101" in names
    assert "so_arm101_leader" in names


def test_lookup_unknown_vid_pid_returns_empty() -> None:
    assert lookup_by_vid_pid(vid="dead", pid="beef") == []
