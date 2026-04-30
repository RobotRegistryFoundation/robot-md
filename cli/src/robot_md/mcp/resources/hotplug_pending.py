"""robot-md://hotplug/pending — read-only view over SP-HP's pending events.

Subscribers receive notifications/resources/updated on socket-nudge (Linux)
or file-poll-detected change (macOS / Windows). The notification wiring
lives in resource_subscribers.py + the FastMCP lifespan hook in server.py.
"""

from __future__ import annotations

import json

from robot_md.hotplug.queue import EventQueue


URI = "robot-md://hotplug/pending"


def build_pending_payload(*, _queue: EventQueue | None = None) -> dict:
    q = _queue or EventQueue()
    if not q.path.exists():
        return {"pending": []}

    records: list[dict] = []
    for line in q.path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except Exception:
            continue

    resolved_refs = {
        r["ref"] for r in records
        if r.get("kind") == "resolved" and r.get("ref")
    }

    pending: list[dict] = []
    for r in records:
        if r.get("kind") != "pending":
            continue
        if r["id"] in resolved_refs:
            continue
        pending.append({
            "event_id": r["id"],
            "tier": r["decision"]["tier"],
            "device": r["event"],
            "decision": r["decision"],
        })
    return {"pending": pending}
