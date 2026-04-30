from __future__ import annotations

from pathlib import Path

from robot_md.hotplug.event import DeviceEvent
from robot_md.hotplug.matcher import Decision
from robot_md.hotplug.queue import EventQueue, last_reject_ts_for_event


def _evt(serial="AB12", path="/dev/ttyACM0") -> DeviceEvent:
    return DeviceEvent(
        kind="tty_added", vid="1a86", pid="7523", serial=serial,
        path=path, transport="feetech",
        raw_metadata={}, detected_at="2026-04-27T19:30:11Z",
    )


def test_no_history_returns_none(tmp_path: Path) -> None:
    q = EventQueue(path=tmp_path / "q.jsonl")
    assert last_reject_ts_for_event(q, _evt()) is None


def test_returns_ts_of_matching_reject(tmp_path: Path) -> None:
    q = EventQueue(path=tmp_path / "q.jsonl")
    pending = q.append_pending(_evt(), Decision(tier="HIGH", unambiguous=True, bind_proposal=None))
    rec = q.append_resolution(ref_id=pending.id, resolution="reject", by="user", outcome=None)
    ts = last_reject_ts_for_event(q, _evt())
    assert ts == rec.ts


def test_ignores_rejects_for_other_devices(tmp_path: Path) -> None:
    q = EventQueue(path=tmp_path / "q.jsonl")
    pending = q.append_pending(
        _evt(serial="OTHER"),
        Decision(tier="HIGH", unambiguous=True, bind_proposal=None),
    )
    q.append_resolution(ref_id=pending.id, resolution="reject", by="user", outcome=None)
    assert last_reject_ts_for_event(q, _evt()) is None  # different serial
