from __future__ import annotations

from pathlib import Path

from robot_md.hotplug.event import DeviceEvent
from robot_md.hotplug.matcher import Decision
from robot_md.hotplug.queue import EventQueue
from robot_md.mcp.tools.hotplug_confirm import hotplug_confirm_tool


def test_reject_appends_resolution_no_manifest_change(tmp_path: Path) -> None:
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("---\nid: RRN-test\nmetadata: {a: 1}\ndrivers: []\n---\n")
    before = manifest.read_text()
    q = EventQueue(path=tmp_path / "q.jsonl")
    pending = q.append_pending(
        DeviceEvent(
            kind="tty_added",
            vid="1a86",
            pid="7523",
            serial=None,
            path="/dev/ttyACM0",
            transport="feetech",
            raw_metadata={},
            detected_at="2026-04-27T19:30:11Z",
        ),
        Decision(tier="MEDIUM", unambiguous=False, bind_proposal=None),
    )
    out = hotplug_confirm_tool(
        event_id=pending.id,
        decision="reject",
        choice_index=None,
        _queue=q,
        _manifest_path=manifest,
        _by="claude",
    )
    assert out["ok"] is True
    assert manifest.read_text() == before
    assert '"resolution": "reject"' in (tmp_path / "q.jsonl").read_text()
