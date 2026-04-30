"""End-to-end: when run_daemon_with_socket processes an event, a connected
subscriber receives a 1-byte nudge.

This is the proof point that SP-HP's broadcast extension is actually
wired through the daemon's event_loop — not just present on
SocketListener as an unused method.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from robot_md.hotplug.daemon import run_daemon_with_socket
from robot_md.hotplug.event import DeviceEvent


pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Unix socket — Linux primary")


def _evt():
    return DeviceEvent(
        kind="tty_added", vid="dead", pid="beef", serial=None,
        path="/dev/ttyACM0", transport="unknown",
        raw_metadata={}, detected_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )


def test_daemon_broadcasts_nudge_to_subscriber_on_event(tmp_path: Path) -> None:
    sock_path = tmp_path / "hotplug.sock"
    received: list[bytes] = []
    release_event = asyncio.Event()

    async def watcher():
        # Wait until the test has a subscriber connected, then yield one
        # event. After that, idle until cancellation.
        await release_event.wait()
        yield _evt()
        await asyncio.Future()

    stop = asyncio.Event()

    async def main():
        daemon_task = asyncio.create_task(run_daemon_with_socket(
            stop_event=stop,
            queue_path=tmp_path / "q.jsonl",
            audit_root=tmp_path / "audit",
            watcher_factory=watcher,
            socket_path=sock_path,
        ))

        # Wait for the daemon to bind the socket.
        for _ in range(50):
            if sock_path.exists():
                break
            await asyncio.sleep(0.02)
        assert sock_path.exists(), "daemon never bound the socket"

        reader, writer = await asyncio.open_unix_connection(str(sock_path))
        try:
            # Give asyncio a tick to register the subscriber's writer.
            await asyncio.sleep(0.05)
            release_event.set()  # let the watcher emit its event

            data = await asyncio.wait_for(reader.read(1), timeout=2.0)
            received.append(data)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

        stop.set()
        await asyncio.wait_for(daemon_task, timeout=2.0)

    asyncio.run(main())
    assert received == [b"\x01"]
