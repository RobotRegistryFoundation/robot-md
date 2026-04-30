"""Linux pyudev-based real-time device watcher. <50ms latency."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from robot_md.hotplug.event import DeviceEvent, classify_transport


async def watch_devices() -> AsyncIterator[DeviceEvent]:
    import pyudev

    ctx = pyudev.Context()
    monitor = pyudev.Monitor.from_netlink(ctx)
    monitor.filter_by(subsystem="usb")
    monitor.filter_by(subsystem="tty")
    monitor.start()

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def _drain() -> None:
        for action, device in monitor:
            if action != "add":
                continue
            evt = _device_to_event(device)
            asyncio.run_coroutine_threadsafe(queue.put(evt), loop)

    loop.run_in_executor(None, _drain)

    while True:
        evt = await queue.get()
        yield evt


def _device_to_event(device) -> DeviceEvent:
    vid = device.get("ID_VENDOR_ID")
    pid = device.get("ID_MODEL_ID")
    serial = device.get("ID_SERIAL_SHORT")
    subsystem = device.subsystem
    return DeviceEvent(
        kind=("tty_added" if subsystem == "tty" else "usb_added"),
        vid=vid,
        pid=pid,
        serial=serial,
        path=device.device_node or "",
        transport=classify_transport(vid=vid, pid=pid, subsystem=subsystem),
        raw_metadata={},
        detected_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )
