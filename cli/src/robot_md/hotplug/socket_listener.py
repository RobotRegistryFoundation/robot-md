"""Unix socket listener for MCP-server nudges. Linux-primary; the
daemon falls back to file-poll on macOS / Windows when no listener is
available.

A nudge is any inbound bytes — payload content is ignored. Presence of
a connection means 'check the queue now'.

We bind the AF_UNIX socket ourselves rather than letting
asyncio.start_unix_server do it, because asyncio silently removes any
existing socket file before binding. That auto-unlink would let a
second daemon hijack the path while the first is still alive.
Pre-binding via the raw socket API surfaces EADDRINUSE so a duplicate
daemon fails-loud — see Task 16's exit-code-2 protection.
"""

from __future__ import annotations

import asyncio
import os
import socket as _socket
from pathlib import Path
from typing import Callable

_DEFAULT_PATH = (
    Path(f"/run/user/{os.getuid()}/robot-md-hotplug.sock")
    if hasattr(os, "getuid") else None
)


class SocketListener:
    def __init__(self, *, path: Path | None = None) -> None:
        if path is None and _DEFAULT_PATH is None:
            raise RuntimeError("SocketListener has no default path on this platform")
        self.path = path or _DEFAULT_PATH
        self._server: asyncio.AbstractServer | None = None
        self._sock: _socket.socket | None = None

    async def start(self, *, on_nudge: Callable[[], None]) -> None:
        async def handler(reader, writer):
            try:
                await reader.read(64)  # discard payload — presence is the nudge
                on_nudge()
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass

        self.path.parent.mkdir(parents=True, exist_ok=True)
        sock = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
        try:
            sock.bind(str(self.path))
        except OSError:
            sock.close()
            raise
        sock.listen()
        sock.setblocking(False)
        self._sock = sock
        # cleanup_socket=False because we own the file lifecycle in stop().
        self._server = await asyncio.start_unix_server(
            handler, sock=sock, cleanup_socket=False,
        )

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        self._sock = None
        try:
            if self.path.exists():
                self.path.unlink()
        except OSError:
            pass
