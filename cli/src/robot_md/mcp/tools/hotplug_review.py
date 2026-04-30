"""MCP tool: hotplug_review — list pending (un-resolved) hot-plug events."""

from __future__ import annotations

import json

from robot_md.hotplug.queue import EventQueue


def hotplug_review_tool(_queue: EventQueue | None = None) -> dict:
    q = _queue or EventQueue()
    records = []
    for line in q.path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except Exception:
            continue
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
    return {"pending": out}
