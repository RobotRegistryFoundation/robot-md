"""SP-AN Task 4: FilePollFallback does NOT fire on the initial-baseline
read or while the queue is steady-state — subscribers should receive
zero spurious notifications."""

from __future__ import annotations

import asyncio
from pathlib import Path

from robot_md.mcp.resource_subscribers import FilePollFallback


def test_no_change_no_event(tmp_path: Path) -> None:
    queue_path = tmp_path / "q.jsonl"
    queue_path.write_text("seed\n")
    received: list[int] = []

    poller = FilePollFallback(
        queue_path=queue_path,
        on_change=lambda: received.append(1),
        interval=0.02,
    )

    async def main() -> None:
        await poller.start()
        await asyncio.sleep(0.15)
        await poller.stop()

    asyncio.run(main())
    assert received == []


def test_initial_start_does_not_fire(tmp_path: Path) -> None:
    """Subscriber connects to a queue that already has records; first
    poll must NOT count that as a change."""
    queue_path = tmp_path / "q.jsonl"
    queue_path.write_text('{"id":"evt_old","kind":"pending"}\n{"id":"evt_old2","kind":"pending"}\n')
    received: list[int] = []

    poller = FilePollFallback(
        queue_path=queue_path,
        on_change=lambda: received.append(1),
        interval=0.02,
    )

    async def main() -> None:
        await poller.start()
        # Multiple poll cycles with no writes; baseline must hold.
        await asyncio.sleep(0.1)
        await poller.stop()

    asyncio.run(main())
    assert received == []
