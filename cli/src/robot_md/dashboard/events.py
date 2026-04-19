"""Event log + live broadcast for the dev dashboard.

Design: MCP server owns an EventPublisher (writes JSONL + broadcasts on a local
WS port). Dashboard owns an EventLog (tails the JSONL + subscribes to WS). The
JSONL is the durable record; the WS is the live pipe.
"""

from __future__ import annotations

import asyncio
import contextlib
import gzip
import json
import queue
import threading
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROTATE_BYTES = 10 * 1024 * 1024  # 10 MB
ROTATE_KEEP = 3
FRAME_MIN_INTERVAL_S = 5.0  # throttle for frame events


@dataclass(frozen=True)
class Event:
    kind: str
    ts: float
    data: dict[str, Any]

    def to_jsonl(self) -> str:
        return json.dumps({"kind": self.kind, "ts": self.ts, "data": self.data}) + "\n"

    @classmethod
    def from_jsonl(cls, line: str) -> Event:
        obj = json.loads(line)
        return cls(kind=obj["kind"], ts=float(obj["ts"]), data=obj.get("data") or {})


class EventPublisher:
    """Runs in the MCP server. publish() is non-blocking."""

    def __init__(self, *, jsonl_path: Path, ws_port: int | None = 8092) -> None:
        self.jsonl_path = Path(jsonl_path)
        self.ws_port = ws_port
        self._q: queue.Queue[Event] = queue.Queue(maxsize=1024)
        self._stop = threading.Event()
        self._writer_thread: threading.Thread | None = None
        self._ws_thread: threading.Thread | None = None
        self._ws_clients: set = set()
        self._ws_lock = threading.Lock()
        self._last_frame_ts = 0.0

    def start(self) -> None:
        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        self._writer_thread = threading.Thread(target=self._writer_loop, daemon=True)
        self._writer_thread.start()
        if self.ws_port is not None:
            self._ws_thread = threading.Thread(target=self._ws_serve_loop, daemon=True)
            self._ws_thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._writer_thread:
            self._writer_thread.join(timeout=2.0)

    def publish(self, kind: str, data: dict) -> None:
        import robot_md.dashboard.events as _mod

        now = time.time()
        if kind == "frame":
            if now - self._last_frame_ts < _mod.FRAME_MIN_INTERVAL_S:
                return
            self._last_frame_ts = now
        evt = Event(kind=kind, ts=now, data=dict(data))
        # Publisher refuses to block the hot path — drop on full queue.
        with contextlib.suppress(queue.Full):
            self._q.put_nowait(evt)

    # ------------------------------------------------------- writer thread

    def _writer_loop(self) -> None:
        while not self._stop.is_set() or not self._q.empty():
            try:
                evt = self._q.get(timeout=0.1)
            except queue.Empty:
                continue
            line = evt.to_jsonl()
            self._append_and_rotate(line)
            self._broadcast_ws(line)

    def _append_and_rotate(self, line: str) -> None:
        import robot_md.dashboard.events as _mod

        p = self.jsonl_path
        with p.open("a") as f:
            f.write(line)
        try:
            size = p.stat().st_size
        except FileNotFoundError:
            return
        if size < _mod.ROTATE_BYTES:
            return
        # Rotate: events.jsonl → events.1.jsonl.gz; shift existing rotations.
        for i in range(ROTATE_KEEP, 0, -1):
            src = p.with_name(f"{p.stem}.{i}.jsonl.gz")
            dst = p.with_name(f"{p.stem}.{i + 1}.jsonl.gz")
            if src.exists():
                if i == ROTATE_KEEP:
                    src.unlink()
                else:
                    src.rename(dst)
        rotated = p.with_name(f"{p.stem}.1.jsonl.gz")
        with p.open("rb") as src, gzip.open(rotated, "wb") as dst:
            dst.write(src.read())
        p.unlink()
        p.touch()

    # ---------------------------------------------------- WS broadcast

    def _ws_serve_loop(self) -> None:
        try:
            import websockets  # noqa: F401
        except Exception:
            return
        try:
            asyncio.run(self._ws_server_async())
        except Exception:
            return

    async def _ws_server_async(self) -> None:
        try:
            import websockets

            loop = asyncio.get_event_loop()

            async def handler(websocket):
                with self._ws_lock:
                    self._ws_clients.add((websocket, loop))
                try:
                    await websocket.wait_closed()
                finally:
                    with self._ws_lock:
                        self._ws_clients.discard((websocket, loop))

            port = self.ws_port if self.ws_port and self.ws_port > 0 else 0
            async with websockets.serve(handler, "127.0.0.1", port):
                while not self._stop.is_set():
                    await asyncio.sleep(0.1)
        except Exception:
            return

    def _broadcast_ws(self, line: str) -> None:
        with self._ws_lock:
            clients = list(self._ws_clients)
        for ws, loop in clients:
            try:
                fut = asyncio.run_coroutine_threadsafe(ws.send(line), loop)
                fut.result(timeout=0.05)
            except Exception:
                pass


class EventLog:
    """Runs in the dashboard. snapshot() reads JSONL; tail() yields live events."""

    def __init__(
        self,
        *,
        jsonl_path: Path,
        ws_url: str | None = "ws://127.0.0.1:8092/events",
        poll_interval_s: float = 0.5,
    ) -> None:
        self.jsonl_path = Path(jsonl_path)
        self.ws_url = ws_url
        self.poll_interval_s = poll_interval_s

    async def snapshot(self, *, n: int = 200) -> list[Event]:
        """Return last N events across current JSONL + most recent rotation."""
        lines: list[str] = []
        current = self.jsonl_path
        rotated = current.with_name(f"{current.stem}.1.jsonl.gz")
        if rotated.exists():
            with gzip.open(rotated, "rt") as f:
                lines.extend(f.readlines())
        if current.exists():
            lines.extend(current.read_text().splitlines(keepends=True))
        out: list[Event] = []
        for line in lines[-n:]:
            line = line if line.endswith("\n") else line + "\n"
            try:
                out.append(Event.from_jsonl(line))
            except Exception:
                continue
        return out

    async def tail(self) -> AsyncIterator[Event]:
        """Yield live events by polling the JSONL file.

        WS subscription is a v2 enhancement; current implementation uses polling
        only. The poll_interval_s controls latency.
        """
        pos = 0
        if self.jsonl_path.exists():
            pos = self.jsonl_path.stat().st_size
        while True:
            try:
                size = self.jsonl_path.stat().st_size if self.jsonl_path.exists() else 0
            except FileNotFoundError:
                size = 0
            if size > pos:
                with self.jsonl_path.open("r") as f:
                    f.seek(pos)
                    for line in f:
                        if line.strip():
                            with contextlib.suppress(Exception):
                                yield Event.from_jsonl(line)
                    pos = f.tell()
            elif size < pos:
                pos = 0
            await asyncio.sleep(self.poll_interval_s)
