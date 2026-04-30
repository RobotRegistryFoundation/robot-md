from __future__ import annotations

from pathlib import Path

from robot_md.hotplug.event import DeviceEvent
from robot_md.hotplug.matcher import Decision
from robot_md.hotplug.queue import EventQueue
from robot_md.mcp.tools.hotplug_review import hotplug_review_tool


def _evt():
    return DeviceEvent(
        kind="tty_added", vid="1a86", pid="7523", serial="AB12",
        path="/dev/ttyACM0", transport="feetech",
        raw_metadata={}, detected_at="2026-04-27T19:30:11Z",
    )


def test_review_returns_pending_only(tmp_path: Path) -> None:
    q = EventQueue(path=tmp_path / "q.jsonl")
    pending1 = q.append_pending(_evt(), Decision(tier="MEDIUM", unambiguous=False, bind_proposal=None))
    pending2 = q.append_pending(_evt(), Decision(tier="LOW", unambiguous=False, bind_proposal=None))
    q.append_resolution(ref_id=pending1.id, resolution="bind", by="claude", outcome={})

    result = hotplug_review_tool(_queue=q)
    ids = {entry["event_id"] for entry in result["pending"]}
    assert pending2.id in ids
    assert pending1.id not in ids
