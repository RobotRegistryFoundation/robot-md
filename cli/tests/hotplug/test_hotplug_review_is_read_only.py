"""hotplug_review must not write: no queue file created, nothing appended."""

from __future__ import annotations

from pathlib import Path

import pytest

from robot_md.hotplug import queue as queue_mod
from robot_md.hotplug.event import DeviceEvent
from robot_md.hotplug.matcher import Decision
from robot_md.hotplug.queue import EventQueue
from robot_md.mcp.resources.hotplug_pending import build_pending_payload
from robot_md.mcp.tools.hotplug_review import hotplug_review_tool


def _point_default_queue_at(monkeypatch, path: Path) -> None:
    """Redirect the default queue path, including EventQueue's bound default,
    so a reader that still opens an EventQueue writes under tmp_path (and the
    test catches it) instead of touching the real ~/.robot-md."""
    monkeypatch.setattr(queue_mod, "_DEFAULT_PATH", path)
    monkeypatch.setattr(EventQueue.__init__, "__kwdefaults__", {"path": path})


def test_review_does_not_create_missing_queue(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "robot-md" / "hotplug-events.jsonl"
    _point_default_queue_at(monkeypatch, path)

    assert hotplug_review_tool() == {"pending": []}
    assert build_pending_payload() == {"pending": []}
    assert not path.exists()
    assert not path.parent.exists()


@pytest.mark.parametrize("reader", ["tool", "resource"])
def test_review_does_not_append_on_malformed_lines(tmp_path: Path, monkeypatch, reader) -> None:
    path = tmp_path / "hotplug-events.jsonl"
    q = EventQueue(path=path)
    pending = q.append_pending(
        DeviceEvent(
            kind="tty_added",
            vid="1a86",
            pid="7523",
            serial="AB12",
            path="/dev/ttyACM0",
            transport="feetech",
            raw_metadata={},
            detected_at="2026-04-27T19:30:11Z",
        ),
        Decision(tier="LOW", unambiguous=False, bind_proposal=None),
    )
    with path.open("a") as f:
        f.write("{not json\n")
    before = path.read_bytes()
    _point_default_queue_at(monkeypatch, path)

    out = hotplug_review_tool() if reader == "tool" else build_pending_payload()

    assert [e["event_id"] for e in out["pending"]] == [pending.id]
    if reader == "tool":
        assert out["malformed_lines"] == 1
    assert path.read_bytes() == before
