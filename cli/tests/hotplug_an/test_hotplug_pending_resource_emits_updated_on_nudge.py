"""SP-AN Task 3: HotplugResourceSubscriber as a CLIENT of the SP-HP
daemon's broadcast socket, exercised against the real SocketListener
(commits 742cfd0 + 9ccb484 made the daemon actually broadcast)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from robot_md.hotplug.socket_listener import SocketListener
from robot_md.mcp.resource_subscribers import HotplugResourceSubscriber


pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Unix socket — Linux primary")


async def _wait_for_subscriber(listener: SocketListener) -> None:
    for _ in range(100):
        if listener.subscriber_count >= 1:
            return
        await asyncio.sleep(0.02)
    raise AssertionError("subscriber never connected")


def test_subscriber_fires_on_change_when_daemon_broadcasts(tmp_path: Path) -> None:
    sock_path = tmp_path / "h.sock"
    received: list[int] = []

    async def main():
        listener = SocketListener(path=sock_path)
        await listener.start()
        try:
            sub = HotplugResourceSubscriber(
                socket_path=sock_path,
                on_change=lambda: received.append(1),
            )
            await sub.start()
            await _wait_for_subscriber(listener)
            await listener.broadcast()
            for _ in range(50):
                if received:
                    break
                await asyncio.sleep(0.02)
            await sub.stop()
        finally:
            await listener.stop()

    asyncio.run(main())
    assert received == [1]


def test_subscriber_supports_async_on_change(tmp_path: Path) -> None:
    sock_path = tmp_path / "h.sock"
    received: list[str] = []

    async def main():
        listener = SocketListener(path=sock_path)
        await listener.start()
        try:
            async def on_change() -> None:
                received.append("async")

            sub = HotplugResourceSubscriber(socket_path=sock_path, on_change=on_change)
            await sub.start()
            await _wait_for_subscriber(listener)
            await listener.broadcast()
            for _ in range(50):
                if received:
                    break
                await asyncio.sleep(0.02)
            await sub.stop()
        finally:
            await listener.stop()

    asyncio.run(main())
    assert received == ["async"]


def test_subscriber_returns_quietly_if_socket_missing(tmp_path: Path) -> None:
    received: list[int] = []
    sub = HotplugResourceSubscriber(
        socket_path=tmp_path / "doesnt-exist.sock",
        on_change=lambda: received.append(1),
    )

    async def main():
        await sub.start()
        await asyncio.sleep(0.05)
        await sub.stop()

    asyncio.run(main())
    assert received == []
