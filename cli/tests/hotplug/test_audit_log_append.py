from __future__ import annotations

import json
from pathlib import Path

from robot_md.hotplug.audit import AuditLog


def test_append_chains_per_rrn(tmp_path: Path) -> None:
    log = AuditLog(rrn="RRN-test", root=tmp_path / "audit")
    log.append("hotplug_event", {"foo": "bar"})
    log.append("hotplug_bind", {"driver_id": "arm_servos"})
    contents = (tmp_path / "audit" / "RRN-test.jsonl").read_text().splitlines()
    assert len(contents) == 2
    rec1 = json.loads(contents[0])
    rec2 = json.loads(contents[1])
    assert rec2["prev_hash"] == rec1["this_hash"]
