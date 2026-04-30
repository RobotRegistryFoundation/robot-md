from __future__ import annotations

from pathlib import Path

from robot_md.hotplug.event import DeviceEvent
from robot_md.hotplug.matcher import Decision
from robot_md.hotplug.queue import EventQueue


def _evt() -> DeviceEvent:
    return DeviceEvent(
        kind="tty_added", vid="1a86", pid="7523", serial=None,
        path="/dev/ttyACM0", transport="feetech",
        raw_metadata={}, detected_at="2026-04-27T19:30:11Z",
    )


def test_corrupt_last_line_drops_to_alert_and_continues(tmp_path: Path) -> None:
    q = EventQueue(path=tmp_path / "q.jsonl")
    q.append_pending(_evt(), Decision(tier="LOW", unambiguous=False, bind_proposal=None))
    # Corrupt the file by appending a partial line.
    with (tmp_path / "q.jsonl").open("ab") as f:
        f.write(b'{"id":"truncat')
    q2 = EventQueue(path=tmp_path / "q.jsonl")
    pending = q2.append_pending(_evt(), Decision(tier="LOW", unambiguous=False, bind_proposal=None))
    contents = (tmp_path / "q.jsonl").read_text()
    assert "daemon_alert" in contents
    assert pending.kind == "pending"  # subsequent append still works
