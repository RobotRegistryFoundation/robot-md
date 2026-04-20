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

    def backfill_from_jsonl(
        self,
        path,
        manifest_path: str,
        n: int = 100,
    ) -> None:
        """Replay up to n paired invocations for `manifest_path` from `path`.

        Filter rules:
        - Only tool.call / tool.result events participate.
        - Events whose payload `manifest_path` ≠ the arg are ignored.
        - Unpaired tool.call events are dropped.
        - Malformed JSON lines are skipped (logged at WARNING).
        - Missing file is a no-op.

        Called once at load_context; never raises. Appends newest records
        into the ring in chronological order so callers observe a correct
        deque state post-backfill.
        """
        import json
        import logging
        from pathlib import Path as _Path

        log = logging.getLogger(__name__)
        p = _Path(path)
        if not p.exists():
            return

        # Single forward scan — cheap, and order-preserving. We pair by
        # request_id using a small live map; emit an InvocationRecord the
        # moment the result event lands.
        pending: dict[str, dict] = {}
        pairs: list[tuple[dict, dict]] = []
        try:
            with p.open("r") as f:
                for raw in f:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        evt = json.loads(raw)
                    except Exception:
                        log.warning("backfill: skipping malformed line")
                        continue
                    kind = evt.get("kind")
                    data = evt.get("data") or {}
                    if data.get("manifest_path") != manifest_path:
                        continue
                    if kind == "tool.call":
                        rid = data.get("request_id")
                        if rid:
                            pending[rid] = evt
                    elif kind == "tool.result":
                        rid = data.get("request_id")
                        if rid and rid in pending:
                            pairs.append((pending.pop(rid), evt))
        except OSError as e:
            log.warning("backfill: read error: %s", e)
            return

        # Keep only last n pairs, append oldest-first so the ring ends up
        # with newest at the right end (matches runtime append order).
        from robot_md.mcp.invocation_record import InvocationRecord

        for call_evt, result_evt in pairs[-n:]:
            try:
                rec = InvocationRecord.from_event_pair(call_evt, result_evt)
            except Exception:
                log.warning("backfill: could not build record; skipping")
                continue
            self.append(rec)
