"""robot-md://hotplug/pending — read-only view over SP-HP's pending events.

Subscribers receive notifications/resources/updated on socket-nudge (Linux)
or file-poll-detected change (macOS / Windows). The notification wiring
lives in resource_subscribers.py + the FastMCP lifespan hook in server.py.
"""

from __future__ import annotations

from robot_md.hotplug import queue as _queue_mod
from robot_md.hotplug.queue import EventQueue, _safe_iter_records

URI = "robot-md://hotplug/pending"


def build_pending_payload(*, _queue: EventQueue | None = None) -> dict:
    # Read the file directly: constructing an EventQueue creates the file
    # when missing and appends a daemon_alert on malformed lines.
    path = _queue.path if _queue is not None else _queue_mod._DEFAULT_PATH
    records, _ = _safe_iter_records(path)

    resolved_refs = {r["ref"] for r in records if r.get("kind") == "resolved" and r.get("ref")}

    pending: list[dict] = []
    for r in records:
        if r.get("kind") != "pending":
            continue
        if r["id"] in resolved_refs:
            continue
        pending.append(
            {
                "event_id": r["id"],
                "tier": r["decision"]["tier"],
                "device": r["event"],
                "decision": r["decision"],
            }
        )
    return {"pending": pending}
