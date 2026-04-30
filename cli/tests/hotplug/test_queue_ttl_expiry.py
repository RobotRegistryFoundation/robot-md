from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from robot_md.hotplug.event import DeviceEvent
from robot_md.hotplug.matcher import Decision
from robot_md.hotplug.queue import EventQueue


def _evt() -> DeviceEvent:
    return DeviceEvent(
        kind="tty_added",
        vid="1a86",
        pid="7523",
        serial=None,
        path="/dev/ttyACM0",
        transport="feetech",
        raw_metadata={},
        detected_at=(
            (datetime.now(timezone.utc) - timedelta(days=10)).isoformat().replace("+00:00", "Z")
        ),
    )


def test_expire_pending_older_than_ttl(tmp_path: Path) -> None:
    q = EventQueue(path=tmp_path / "q.jsonl")
    medium = Decision(tier="MEDIUM", unambiguous=False, bind_proposal=None)
    pending = q.append_pending(_evt(), medium)
    expired_ids = q.expire_old(ttl_days=1)
    assert pending.id in expired_ids
    contents = (tmp_path / "q.jsonl").read_text()
    assert '"resolution": "expired"' in contents
