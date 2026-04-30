"""Windows device watcher. WM_DEVICECHANGE preferred; polling fallback."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from robot_md.hotplug.event import DeviceEvent, classify_transport

_POLL_INTERVAL_S = 1.5


def _enumerate_windows() -> set[tuple]:
    """Return {(vid, pid, serial, path), ...} via pyserial.list_ports."""
    out: set[tuple] = set()
    try:
        from serial.tools import list_ports

        for p in list_ports.comports():
            vid = f"{p.vid:04x}" if p.vid else None
            pid = f"{p.pid:04x}" if p.pid else None
            out.add((vid, pid, p.serial_number, p.device))
    except Exception:
        pass
    return out


async def watch_devices() -> AsyncIterator[DeviceEvent]:
    """Polling fallback. The WM_DEVICECHANGE message-pump path is wired up
    in Task 5's daemon entry when running under the systemtray app stub.
    For test + headless service contexts, polling is sufficient."""
    seen = _enumerate_windows()
    while True:
        await asyncio.sleep(_POLL_INTERVAL_S)
        current = _enumerate_windows()
        new = current - seen
        seen = current
        for vid, pid, serial, path in new:
            yield DeviceEvent(
                kind="tty_added",
                vid=vid,
                pid=pid,
                serial=serial,
                path=path,
                transport=classify_transport(vid=vid, pid=pid, subsystem="tty"),
                raw_metadata={},
                detected_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            )
