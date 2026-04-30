from __future__ import annotations

import asyncio
import socket
import sys
from pathlib import Path

import pytest

from robot_md.hotplug.socket_listener import SocketListener


pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Unix socket — Linux primary")


def test_socket_bind_and_nudge(tmp_path: Path) -> None:
    sock_path = tmp_path / "test.sock"
    listener = SocketListener(path=sock_path)
    received: list = []

    async def serve():
        await listener.start(on_nudge=lambda: received.append(1))
        # Simulate a client nudge.
        c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        c.connect(str(sock_path))
        c.sendall(b"\x01")
        c.close()
        await asyncio.sleep(0.05)
        await listener.stop()

    asyncio.run(serve())
    assert received == [1]


def test_second_listener_eaddrinuse(tmp_path: Path) -> None:
    sock_path = tmp_path / "test.sock"
    listener = SocketListener(path=sock_path)
    other = SocketListener(path=sock_path)

    async def main():
        await listener.start(on_nudge=lambda: None)
        with pytest.raises(OSError):
            await other.start(on_nudge=lambda: None)
        await listener.stop()

    asyncio.run(main())
