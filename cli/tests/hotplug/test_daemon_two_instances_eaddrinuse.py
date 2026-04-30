from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from robot_md.hotplug.daemon import run_daemon_with_socket
from robot_md.hotplug.socket_listener import SocketListener

pytestmark = pytest.mark.skipif(
    sys.platform != "linux",
    reason="socket-bind contention is Linux-only",
)


async def _empty_watcher():
    if False:
        yield


def test_second_daemon_exits_with_eaddrinuse(tmp_path: Path) -> None:
    sock_path = tmp_path / "hotplug.sock"
    listener = SocketListener(path=sock_path)
    stop2 = asyncio.Event()

    async def main():
        # Pre-bind the socket to simulate a running daemon.
        await listener.start()
        try:
            rc = await run_daemon_with_socket(
                stop_event=stop2,
                queue_path=tmp_path / "q.jsonl",
                audit_root=tmp_path / "audit",
                watcher_factory=_empty_watcher,
                socket_path=sock_path,
            )
            assert rc == 2
        finally:
            await listener.stop()

    asyncio.run(main())
