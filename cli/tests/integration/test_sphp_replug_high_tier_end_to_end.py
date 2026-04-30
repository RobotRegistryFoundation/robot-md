from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from robot_md.hotplug.daemon import run_daemon
from robot_md.hotplug.event import DeviceEvent
from robot_md.hotplug.presets_index import PresetMatch


def _evt():
    return DeviceEvent(
        kind="tty_added",
        vid="1a86",
        pid="7523",
        serial="UNIQUE_SERIAL",
        path="/dev/ttyACM0",
        transport="feetech",
        raw_metadata={},
        detected_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )


def test_high_tier_auto_bind_writes_manifest(tmp_path: Path) -> None:
    """Daemon classifies HIGH → calls manifest.merge → writes ROBOT.md."""
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("---\nid: RRN-test\nmetadata: {a: 1}\ndrivers: []\n---\n")

    async def watcher():
        yield _evt()

    stop = asyncio.Event()

    async def main():
        with (
            patch(
                "robot_md.hotplug.presets_index.lookup_by_vid_pid",
                lambda *, vid, pid: [PresetMatch("so_arm101", "feetech", "exact_match")],
            ),
            patch(
                "robot_md.hotplug.matcher._installed_backends_for_transport",
                return_value=["lerobot"],
            ),
            patch("pathlib.Path.cwd", return_value=tmp_path),
        ):
            task = asyncio.create_task(
                run_daemon(
                    stop_event=stop,
                    queue_path=tmp_path / "q.jsonl",
                    audit_root=tmp_path / "audit",
                    watcher_factory=watcher,
                )
            )
            await asyncio.sleep(0.1)
            stop.set()
            await asyncio.wait_for(task, timeout=2.0)

    asyncio.run(main())
    text = manifest.read_text()
    assert "backend: lerobot" in text
    assert "id: arm_servos" in text
