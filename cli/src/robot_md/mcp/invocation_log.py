"""Per-McpContext ring buffer of completed tool invocations.

Backs the recent_invocations + recent_errors MCP resources. Populated by
the manifest-stamping publisher wrapper in McpContext at the tool.result
event; backfilled at boot from ~/.robot-md/events.jsonl.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import asdict

from robot_md.mcp.invocation_record import InvocationRecord


class InvocationLog:
    def __init__(self, maxlen: int = 100) -> None:
        self._buf: deque[InvocationRecord] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def append(self, record: InvocationRecord) -> None:
        with self._lock:
            self._buf.append(record)

    def snapshot(self) -> list[dict]:
        with self._lock:
            items = list(self._buf)
        return [asdict(r) for r in reversed(items)]

    def snapshot_errors(self) -> list[dict]:
        return [r for r in self.snapshot() if r["status"] != "ok"]
