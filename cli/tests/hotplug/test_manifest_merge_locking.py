from __future__ import annotations

import threading
from pathlib import Path

from robot_md.hotplug.manifest import merge
from robot_md.hotplug.matcher import BindProposal


def _proposal(driver_id: str) -> BindProposal:
    return BindProposal(
        rrn="RRN-test",
        driver_id_suggestion=driver_id,
        backend_name="lerobot",
        preset_name="so_arm101",
        capability_preview=[],
        inferred_fields={"port": "/dev/ttyACM0", "transport": "feetech"},
    )


def test_concurrent_merges_serialize_via_fcntl(tmp_path: Path) -> None:
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("""---
id: RRN-test
metadata:
  manufacturer: Test
  author: a@b
drivers: []
---
""")
    results: list = []

    def do(driver_id):
        results.append(merge(_proposal(driver_id), manifest_path=manifest))

    t1 = threading.Thread(target=do, args=("driver_one",))
    t2 = threading.Thread(target=do, args=("driver_two",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    text = manifest.read_text()
    assert "driver_one" in text
    assert "driver_two" in text
    assert all(r.success for r in results)
