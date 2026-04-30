from __future__ import annotations

import json
from pathlib import Path

from robot_md.hotplug.event import DeviceEvent
from robot_md.hotplug.matcher import Decision
from robot_md.hotplug.queue import EventQueue
from robot_md.mcp.resources.hotplug_pending import build_pending_payload


def _evt() -> DeviceEvent:
    return DeviceEvent(
        kind="tty_added", vid="1a86", pid="7523", serial="AB12",
        path="/dev/ttyACM0", transport="feetech",
        raw_metadata={}, detected_at="2026-04-27T19:30:11Z",
    )


def test_payload_lists_only_pending_events(tmp_path: Path) -> None:
    q = EventQueue(path=tmp_path / "q.jsonl")
    p1 = q.append_pending(_evt(), Decision(tier="MEDIUM", unambiguous=False, bind_proposal=None))
    p2 = q.append_pending(_evt(), Decision(tier="LOW", unambiguous=False, bind_proposal=None))
    q.append_resolution(ref_id=p1.id, resolution="bind", by="cli", outcome={})

    payload = build_pending_payload(_queue=q)
    pending_ids = {p["event_id"] for p in payload["pending"]}
    assert p2.id in pending_ids
    assert p1.id not in pending_ids


def test_payload_is_json_serializable(tmp_path: Path) -> None:
    q = EventQueue(path=tmp_path / "q.jsonl")
    q.append_pending(_evt(), Decision(tier="MEDIUM", unambiguous=False, bind_proposal=None))
    payload = build_pending_payload(_queue=q)
    json.dumps(payload)


def test_payload_empty_when_queue_missing(tmp_path: Path) -> None:
    queue_path = tmp_path / "q.jsonl"
    q = EventQueue(path=queue_path)
    queue_path.unlink()
    payload = build_pending_payload(_queue=q)
    assert payload == {"pending": []}
