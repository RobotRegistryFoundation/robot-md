"""A repeated hotplug_confirm bind must not write ROBOT.md again.

Before the fix, the second bind merged the driver a second time and only
then learned from the queue that the event was already resolved.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from robot_md.hotplug.event import DeviceEvent
from robot_md.hotplug.manifest import merge
from robot_md.hotplug.matcher import BindProposal, Decision
from robot_md.hotplug.queue import EventQueue
from robot_md.mcp.tools.hotplug_confirm import hotplug_confirm_tool

_MANIFEST = """---
id: RRN-test
metadata: {manufacturer: T, author: a@b}
drivers: []
---
# body
"""


def _proposal(backend: str = "lerobot") -> BindProposal:
    return BindProposal(
        rrn="RRN-test",
        driver_id_suggestion="arm_servos",
        backend_name=backend,
        preset_name="so_arm101",
        capability_preview=[],
        inferred_fields={"port": "/dev/ttyACM0", "transport": "feetech"},
    )


def _pending(q: EventQueue):
    decision = Decision(
        tier="MEDIUM", unambiguous=False, bind_proposal=_proposal(), alternatives=[], reasons=[]
    )
    return q.append_pending(
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
        decision,
    )


def _driver_ids(manifest: Path) -> list[str]:
    front = manifest.read_text().split("---\n")[1]
    return [d["id"] for d in yaml.safe_load(front)["drivers"]]


def _bind(q: EventQueue, manifest: Path, event_id: str) -> dict:
    return hotplug_confirm_tool(
        event_id=event_id, decision="bind", _queue=q, _manifest_path=manifest, _by="claude"
    )


def test_second_bind_leaves_manifest_byte_identical(tmp_path: Path) -> None:
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text(_MANIFEST)
    q = EventQueue(path=tmp_path / "q.jsonl")
    pending = _pending(q)

    first = _bind(q, manifest, pending.id)
    assert first == {"ok": True, "driver_id": "arm_servos"}
    after_first = manifest.read_bytes()
    queue_after_first = q.path.read_bytes()

    second = _bind(q, manifest, pending.id)
    assert second == {"ok": False, "error": "already_resolved", "by": "claude"}
    assert manifest.read_bytes() == after_first
    assert q.path.read_bytes() == queue_after_first
    assert _driver_ids(manifest) == ["arm_servos"]


def test_bind_after_lost_resolution_does_not_duplicate_driver(tmp_path: Path) -> None:
    """The merge landed but the resolution did not: a retry must not re-add."""
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text(_MANIFEST)
    q = EventQueue(path=tmp_path / "q.jsonl")
    pending = _pending(q)
    assert merge(_proposal(), manifest_path=manifest).success
    before = manifest.read_bytes()

    out = _bind(q, manifest, pending.id)
    assert out == {"ok": True, "driver_id": "arm_servos"}
    assert manifest.read_bytes() == before
    assert _driver_ids(manifest) == ["arm_servos"]


def test_merge_refuses_same_id_with_different_driver(tmp_path: Path) -> None:
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text(_MANIFEST)
    assert merge(_proposal(), manifest_path=manifest).success
    before = manifest.read_bytes()

    out = merge(_proposal(backend="other"), manifest_path=manifest)
    assert out.success is False
    assert out.reason.startswith("driver_id_conflict")
    assert manifest.read_bytes() == before
