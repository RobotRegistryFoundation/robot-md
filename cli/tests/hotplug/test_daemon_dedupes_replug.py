from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from robot_md.hotplug.daemon import run_daemon
from robot_md.hotplug.event import DeviceEvent


def _evt():
    return DeviceEvent(
        kind="tty_added",
        vid="1a86",
        pid="7523",
        serial="AB12",
        path="/dev/ttyACM0",
        transport="feetech",
        raw_metadata={},
        detected_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )


def test_replug_within_dedup_window_emits_one_pending(tmp_path: Path) -> None:
    events = [_evt(), _evt(), _evt()]

    async def watcher():
        for e in events:
            yield e

    stop = asyncio.Event()

    async def main():
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
    text = (tmp_path / "q.jsonl").read_text()
    pending_count = text.count('"kind": "pending"')
    assert pending_count == 1
