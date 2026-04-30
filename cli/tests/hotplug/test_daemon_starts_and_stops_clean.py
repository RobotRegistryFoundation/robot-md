from __future__ import annotations

import asyncio
from pathlib import Path

from robot_md.hotplug.daemon import run_daemon


async def _empty_watcher():
    if False:
        yield  # never yields; just an async generator


def test_daemon_runs_until_stop_event(tmp_path: Path) -> None:
    stop = asyncio.Event()

    async def main():
        task = asyncio.create_task(run_daemon(
            stop_event=stop,
            queue_path=tmp_path / "q.jsonl",
            audit_root=tmp_path / "audit",
            watcher_factory=_empty_watcher,
        ))
        await asyncio.sleep(0.05)
        stop.set()
        await asyncio.wait_for(task, timeout=2.0)

    asyncio.run(main())
