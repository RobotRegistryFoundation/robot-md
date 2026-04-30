"""Unix socket fanout for daemon → MCP-server nudges. Linux-primary;
macOS / Windows MCP servers fall back to file-poll.

Direction-of-nudge is daemon-pushes: the daemon (run_daemon_with_socket)
binds this listener at /run/user/$UID/robot-md-hotplug.sock; MCP-server
subscribers connect as clients and read 1-byte nudges from the
connection. Each byte means "the queue changed, re-read it" — payload
content carries no information. The daemon calls broadcast() after
every queue write.

We bind the AF_UNIX socket ourselves rather than letting
asyncio.start_unix_server do it, because asyncio silently removes any
existing socket file before binding. That auto-unlink would let a
second daemon hijack the path while the first is still alive.
Pre-binding via the raw socket API surfaces EADDRINUSE so a duplicate
daemon fails-loud — see daemon.run_daemon_with_socket's rc=2 protection.
"""

from __future__ import annotations

import asyncio
import os
import socket as _socket
from pathlib import Path

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
        self._writers: set[asyncio.StreamWriter] = set()

    async def start(self) -> None:
        async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            self._writers.add(writer)
            try:
                # Hold the connection open until the subscriber disconnects.
                # reader.read() with no length blocks until EOF.
                await reader.read()
            finally:
                self._writers.discard(writer)
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

    async def broadcast(self, byte: bytes = b"\x01") -> int:
        """Push `byte` to every connected subscriber. Drops dead writers
        silently. Returns the count actually delivered to.
        """
        delivered = 0
        dead: list[asyncio.StreamWriter] = []
        for w in list(self._writers):
            try:
                w.write(byte)
                await w.drain()
                delivered += 1
            except (ConnectionResetError, BrokenPipeError, OSError):
                dead.append(w)
        for w in dead:
            self._writers.discard(w)
            try:
                w.close()
            except Exception:
                pass
        return delivered

    @property
    def subscriber_count(self) -> int:
        return len(self._writers)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        for w in list(self._writers):
            try:
                w.close()
            except Exception:
                pass
        self._writers.clear()
        self._sock = None
        try:
            if self.path.exists():
                self.path.unlink()
        except OSError:
            pass
