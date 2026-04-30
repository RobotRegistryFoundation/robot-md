"""SP-AN Task 4: FilePollFallback fires on_change when the queue JSONL
mtime changes (cross-platform fallback path)."""

from __future__ import annotations

import asyncio
from pathlib import Path

from robot_md.mcp.resource_subscribers import FilePollFallback


def test_poll_fires_on_file_mtime_change(tmp_path: Path) -> None:
    queue_path = tmp_path / "q.jsonl"
    queue_path.write_text("")
    received: list[int] = []

    poller = FilePollFallback(
        queue_path=queue_path,
        on_change=lambda: received.append(1),
        interval=0.05,
    )

    async def main() -> None:
        await poller.start()
        await asyncio.sleep(0.1)
        # Daemon-style write: any size change bumps mtime.
        queue_path.write_text('{"id":"evt_1","kind":"pending"}\n')
        for _ in range(50):
            if received:
                break
            await asyncio.sleep(0.02)
        await poller.stop()

    asyncio.run(main())
    assert received, "FilePollFallback did not fire on mtime change"


def test_poll_supports_async_on_change(tmp_path: Path) -> None:
    queue_path = tmp_path / "q.jsonl"
    queue_path.write_text("")
    received: list[str] = []

    async def on_change() -> None:
        received.append("async")

    poller = FilePollFallback(
        queue_path=queue_path,
        on_change=on_change,
        interval=0.05,
    )

    async def main() -> None:
        await poller.start()
        await asyncio.sleep(0.1)
        queue_path.write_text('{"id":"evt_2","kind":"pending"}\n')
        for _ in range(50):
            if received:
                break
            await asyncio.sleep(0.02)
        await poller.stop()

    asyncio.run(main())
    assert received == ["async"]
