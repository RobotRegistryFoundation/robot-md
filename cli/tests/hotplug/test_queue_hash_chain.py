from __future__ import annotations

from pathlib import Path

from robot_md.hotplug.event import DeviceEvent
from robot_md.hotplug.matcher import Decision
from robot_md.hotplug.queue import EventQueue


def _evt() -> DeviceEvent:
    return DeviceEvent(
        kind="tty_added", vid="1a86", pid="7523", serial="AB12",
        path="/dev/ttyACM0", transport="feetech",
        raw_metadata={}, detected_at="2026-04-27T19:30:11Z",
    )


def test_first_record_uses_zero_prev_hash(tmp_path: Path) -> None:
    q = EventQueue(path=tmp_path / "q.jsonl")
    decision = Decision(tier="LOW", unambiguous=False, bind_proposal=None)
    rec = q.append_pending(_evt(), decision)
    assert rec.prev_hash == "sha256:" + ("0" * 64)


def test_second_record_chains_to_first(tmp_path: Path) -> None:
    q = EventQueue(path=tmp_path / "q.jsonl")
    decision = Decision(tier="LOW", unambiguous=False, bind_proposal=None)
    first = q.append_pending(_evt(), decision)
    second = q.append_pending(_evt(), decision)
    assert second.prev_hash == first.this_hash
