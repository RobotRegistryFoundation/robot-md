"""Hot-plug daemon entry point.

run_daemon composes the per-platform watcher with the matcher, queue,
and audit log. It also wires matcher._recent_reject_for to query the
queue at classify-time so the Task 8 demotion is live in production
(Task 8 left the lookup as a stub; daemon installs the real one here).

Phase E delivers run_daemon (Task 15) + run_daemon_with_socket (Task 16,
adds EADDRINUSE protection via the SocketListener).
"""

from __future__ import annotations

import asyncio
import contextlib
import errno
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path

from robot_md.hotplug import matcher
from robot_md.hotplug.audit import AuditLog
from robot_md.hotplug.event import DeviceEvent
from robot_md.hotplug.manifest import merge as manifest_merge
from robot_md.hotplug.matcher import classify
from robot_md.hotplug.queue import EventQueue, last_reject_ts_for_event
from robot_md.hotplug.socket_listener import SocketListener

_DEDUP_WINDOW = timedelta(hours=1)


def _install_recent_reject_provider(queue: EventQueue) -> Callable[[], None]:
    """Rebind matcher._recent_reject_for to a closure over `queue`. Returns a
    callable that restores the original stub — caller can use it to clean up
    after a daemon stops, especially in tests where multiple daemons may
    share the same Python process.
    """
    original = matcher._recent_reject_for

    def query(evt: DeviceEvent) -> str | None:
        return last_reject_ts_for_event(queue, evt)

    matcher._recent_reject_for = query

    def restore() -> None:
        matcher._recent_reject_for = original

    return restore


async def run_daemon(
    *,
    stop_event: asyncio.Event,
    queue_path: Path,
    audit_root: Path,
    watcher_factory: Callable[[], object],
    rrn: str = "RRN-current",
    listener: SocketListener | None = None,
) -> int:
    queue = EventQueue(path=queue_path)
    audit = AuditLog(rrn=rrn, root=audit_root)
    seen: dict[tuple, datetime] = {}
    restore_provider = _install_recent_reject_provider(queue)

    async def _nudge() -> None:
        if listener is not None:
            await listener.broadcast()

    async def event_loop():
        async for evt in watcher_factory():
            if stop_event.is_set():
                break
            key = (evt.vid, evt.pid, evt.serial, evt.path)
            now = datetime.now(timezone.utc)
            last = seen.get(key)
            if last and (now - last) < _DEDUP_WINDOW:
                continue
            seen[key] = now
            decision = classify(evt)
            record = queue.append_pending(evt, decision)
            audit.append(
                "hotplug_event",
                {
                    "event": {
                        "vid": evt.vid,
                        "pid": evt.pid,
                        "serial": evt.serial,
                        "path": evt.path,
                        "transport": evt.transport,
                        "detected_at": evt.detected_at,
                    },
                    "tier": decision.tier,
                },
            )
            await _nudge()
            if (
                decision.tier == "HIGH"
                and decision.unambiguous
                and decision.bind_proposal is not None
            ):
                outcome = manifest_merge(
                    decision.bind_proposal,
                    manifest_path=Path.cwd() / "ROBOT.md",
                )
                if outcome.success:
                    queue.append_resolution(
                        ref_id=record.id,
                        resolution="bind",
                        by="daemon",
                        outcome={"driver_id": outcome.driver_id, "rrn": outcome.rrn},
                    )
                    audit.append("hotplug_bind", {"driver_id": outcome.driver_id})
                else:
                    queue.append_resolution(
                        ref_id=record.id,
                        resolution="bind",
                        by="daemon",
                        outcome={"merge_failed": outcome.reason},
                    )
                    audit.append("merge_failed", {"reason": outcome.reason})
                await _nudge()

    task = asyncio.create_task(event_loop())
    try:
        await stop_event.wait()
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        restore_provider()
    return 0


async def run_daemon_with_socket(
    *,
    stop_event: asyncio.Event,
    queue_path: Path,
    audit_root: Path,
    watcher_factory: Callable[[], object],
    socket_path: Path,
    rrn: str = "RRN-current",
) -> int:
    """run_daemon wrapped with a SocketListener bind. Returns rc=2 if the
    socket path is already in use (another daemon is running).
    """
    listener = SocketListener(path=socket_path)
    try:
        await listener.start()
    except OSError as e:
        if e.errno == errno.EADDRINUSE or "already in use" in str(e).lower():
            return 2
        raise

    try:
        return await run_daemon(
            stop_event=stop_event,
            queue_path=queue_path,
            audit_root=audit_root,
            watcher_factory=watcher_factory,
            rrn=rrn,
            listener=listener,
        )
    finally:
        await listener.stop()
