"""SP-AN resource subscribers — translate SP-HP daemon events into MCP
notifications/resources/updated for the robot-md://hotplug/pending resource.

Two subscribers, one per OS path:

- HotplugResourceSubscriber: connects as a CLIENT to the daemon's Unix
  socket at /run/user/$UID/robot-md-hotplug.sock and reads 1-byte nudges
  in a loop. Linux-primary; macOS/Windows return cleanly when the socket
  doesn't exist.

- FilePollFallback: polls the queue JSONL's mtime. Cross-platform.

The MCP server's lifespan starts both. Either firing triggers on_change,
which (when wired in server.py) calls the latest-captured ServerSession's
send_resource_updated(URI). Active-session tracking is opportunistic per
2026-04-30 spike findings; v1 limitation is documented in
cli/docs/hotplug-roadmap.md.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

_DEFAULT_SOCKET_PATH: Path | None = (
    Path(f"/run/user/{os.getuid()}/robot-md-hotplug.sock") if hasattr(os, "getuid") else None
)


_OnChange = Callable[[], None | Awaitable[None]]


async def _maybe_await(result: Any) -> None:
    if inspect.iscoroutine(result):
        await result


def make_an_emit(state: dict, uri: str) -> Callable[[], Awaitable[None]]:
    """Build the SP-AN emit-closure used by HotplugResourceSubscriber +
    FilePollFallback. The closure looks at state["active_session"] (set
    by the resource handler in build_server) and calls
    send_resource_updated(uri) on it. If the session is gone or the call
    raises, the closure clears state["active_session"] so the next
    resource read recaptures.
    """
    from pydantic import AnyUrl

    emit_uri = AnyUrl(uri)

    async def emit() -> None:
        sess = state.get("active_session")
        if sess is None:
            return
        try:
            await sess.send_resource_updated(emit_uri)
        except Exception:
            state["active_session"] = None

    return emit


class HotplugResourceSubscriber:
    """Linux Unix-socket client that reads 1-byte nudges from the SP-HP
    daemon and invokes on_change for each nudge.

    on_change may be sync or async; if async, it is awaited.
    """

    def __init__(
        self,
        *,
        socket_path: Path | None = None,
        on_change: _OnChange,
    ) -> None:
        self.socket_path = socket_path or _DEFAULT_SOCKET_PATH
        self._on_change = on_change
        self._task: asyncio.Task | None = None
        self._stopping = False

    async def start(self) -> None:
        self._stopping = False
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stopping = True
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _run(self) -> None:
        if self.socket_path is None or not self.socket_path.exists():
            return
        try:
            reader, writer = await asyncio.open_unix_connection(str(self.socket_path))
        except (FileNotFoundError, ConnectionRefusedError, OSError):
            return
        try:
            while not self._stopping:
                data = await reader.read(1)
                if not data:
                    break
                await _maybe_await(self._on_change())
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()


class FilePollFallback:
    """Cross-platform mtime-poll over the queue JSONL.

    Fires on_change on every mtime change after start() — but NOT on the
    initial baseline read, so a steady-state queue produces no spurious
    events.
    """

    def __init__(
        self,
        *,
        queue_path: Path,
        on_change: _OnChange,
        interval: float = 2.0,
    ) -> None:
        self.queue_path = queue_path
        self._on_change = on_change
        self._interval = interval
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        self._stop = asyncio.Event()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _run(self) -> None:
        last_mtime = self._mtime()
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
                return
            except asyncio.TimeoutError:
                pass
            current = self._mtime()
            if current is not None and current != last_mtime:
                last_mtime = current
                await _maybe_await(self._on_change())

    def _mtime(self) -> float | None:
        try:
            return self.queue_path.stat().st_mtime
        except FileNotFoundError:
            return None
