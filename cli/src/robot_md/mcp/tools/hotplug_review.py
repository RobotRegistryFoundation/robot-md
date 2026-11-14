"""MCP tool: hotplug_review — list pending (un-resolved) hot-plug events.

Read-only: it never constructs an EventQueue, whose constructor creates the
queue file when missing and appends a daemon_alert on malformed lines. A
missing queue reads as empty; malformed lines are counted, not recorded.
"""

from __future__ import annotations

from pathlib import Path

from robot_md.hotplug import queue as _queue_mod
from robot_md.hotplug.queue import EventQueue, _safe_iter_records


def hotplug_review_tool(_queue: EventQueue | None = None, _path: Path | None = None) -> dict:
    path = _queue.path if _queue is not None else (_path or _queue_mod._DEFAULT_PATH)
    records, dropped = _safe_iter_records(path)
    pending_ids = {r["id"] for r in records if r.get("kind") == "pending"}
    resolved_refs = {r["ref"] for r in records if r.get("kind") == "resolved" and r.get("ref")}
    pending_unresolved = pending_ids - resolved_refs

    out = []
    for r in records:
        if r.get("kind") == "pending" and r["id"] in pending_unresolved:
            out.append(
                {
                    "event_id": r["id"],
                    "tier": r["decision"]["tier"],
                    "device": r["event"],
                    "decision": r["decision"],
                }
            )
    result: dict = {"pending": out}
    if dropped:
        result["malformed_lines"] = dropped
    return result
