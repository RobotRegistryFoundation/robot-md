from __future__ import annotations

from pathlib import Path

from robot_md.hotplug.event import DeviceEvent
from robot_md.hotplug.matcher import BindProposal, Decision
from robot_md.hotplug.queue import EventQueue
from robot_md.mcp.tools.hotplug_confirm import hotplug_confirm_tool


def test_confirm_bind_writes_manifest_and_appends_resolution(tmp_path: Path) -> None:
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("""---
id: RRN-test
metadata: {manufacturer: T, author: a@b}
drivers: []
---
""")
    q = EventQueue(path=tmp_path / "q.jsonl")
    proposal = BindProposal(
        rrn="RRN-test", driver_id_suggestion="arm_servos",
        backend_name="lerobot", preset_name="so_arm101",
        capability_preview=[],
        inferred_fields={"port": "/dev/ttyACM0", "transport": "feetech"},
    )
    decision = Decision(tier="MEDIUM", unambiguous=False, bind_proposal=proposal,
                        alternatives=[], reasons=[])
    pending = q.append_pending(DeviceEvent(
        kind="tty_added", vid="1a86", pid="7523", serial="AB12",
        path="/dev/ttyACM0", transport="feetech",
        raw_metadata={}, detected_at="2026-04-27T19:30:11Z",
    ), decision)
    out = hotplug_confirm_tool(
        event_id=pending.id, decision="bind", choice_index=None,
        _queue=q, _manifest_path=manifest, _by="claude",
    )
    assert out["ok"] is True
    assert "backend: lerobot" in manifest.read_text()
