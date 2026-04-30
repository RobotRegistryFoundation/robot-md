from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from robot_md.hotplug.socket_listener import SocketListener

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Unix socket — Linux primary")


def test_broadcast_delivers_to_connected_subscriber(tmp_path: Path) -> None:
    """Daemon broadcasts a 1-byte nudge; the subscriber (client) receives it."""
    sock_path = tmp_path / "test.sock"
    listener = SocketListener(path=sock_path)
    received: list[bytes] = []

    async def main():
        await listener.start()
        try:
            reader, writer = await asyncio.open_unix_connection(str(sock_path))

            async def drain():
                while True:
                    data = await reader.read(1)
                    if not data:
                        return
                    received.append(data)

            drain_task = asyncio.create_task(drain())
            # Give asyncio a tick to register the subscriber's writer.
            await asyncio.sleep(0.05)
            assert listener.subscriber_count == 1

            n = await listener.broadcast(b"\x01")
            assert n == 1
            await asyncio.sleep(0.05)

            writer.close()
            await writer.wait_closed()
            await asyncio.wait_for(drain_task, timeout=1.0)
        finally:
            await listener.stop()

    asyncio.run(main())
    assert received == [b"\x01"]


def test_broadcast_with_no_subscribers_is_noop(tmp_path: Path) -> None:
    sock_path = tmp_path / "test.sock"
    listener = SocketListener(path=sock_path)

    async def main():
        await listener.start()
        try:
            assert listener.subscriber_count == 0
            n = await listener.broadcast(b"\x01")
            assert n == 0
        finally:
            await listener.stop()

    asyncio.run(main())


def test_broadcast_drops_dead_subscribers(tmp_path: Path) -> None:
    """A subscriber that disconnects ungracefully is removed from the
    writer set on next broadcast; subsequent broadcasts succeed.
    """
    sock_path = tmp_path / "test.sock"
    listener = SocketListener(path=sock_path)

    async def main():
        await listener.start()
        try:
            _reader, writer = await asyncio.open_unix_connection(str(sock_path))
            await asyncio.sleep(0.05)
            assert listener.subscriber_count == 1

            # Hard-kill the subscriber's transport.
            writer.transport.abort()
            await asyncio.sleep(0.05)

            # Broadcast should not raise; dead writer cleared on next call.
            await listener.broadcast(b"\x01")
            await asyncio.sleep(0.05)
            assert listener.subscriber_count == 0
        finally:
            await listener.stop()

    asyncio.run(main())


def test_second_listener_eaddrinuse(tmp_path: Path) -> None:
    sock_path = tmp_path / "test.sock"
    listener = SocketListener(path=sock_path)
    other = SocketListener(path=sock_path)

    async def main():
        await listener.start()
        with pytest.raises(OSError):
            await other.start()
        await listener.stop()

    asyncio.run(main())
