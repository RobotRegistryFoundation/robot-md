from __future__ import annotations

from pathlib import Path

import pytest

from robot_md.hotplug.event import DeviceEvent
from robot_md.hotplug.matcher import Decision
from robot_md.hotplug.queue import EventQueue, AlreadyResolvedError


def _evt() -> DeviceEvent:
    return DeviceEvent(
        kind="tty_added", vid="1a86", pid="7523", serial="AB12",
        path="/dev/ttyACM0", transport="feetech",
        raw_metadata={}, detected_at="2026-04-27T19:30:11Z",
    )


def test_second_resolution_for_same_event_raises(tmp_path: Path) -> None:
    q = EventQueue(path=tmp_path / "q.jsonl")
    pending = q.append_pending(_evt(), Decision(tier="MEDIUM", unambiguous=False, bind_proposal=None))
    q.append_resolution(ref_id=pending.id, resolution="bind", by="claude", outcome={})
    with pytest.raises(AlreadyResolvedError) as ex:
        q.append_resolution(ref_id=pending.id, resolution="bind", by="cli", outcome={})
    assert "claude" in str(ex.value)
