from __future__ import annotations

import asyncio
import sys

import pytest

from robot_md.hotplug.event import DeviceEvent

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")


def test_watch_devices_emits_event_on_polling_diff(monkeypatch) -> None:
    from robot_md.hotplug import windows as mod

    states = iter([set(), {("1a86", "7523", "ABC", "COM3")}])

    monkeypatch.setattr(mod, "_enumerate_windows", lambda: next(states))
    monkeypatch.setattr(mod, "_POLL_INTERVAL_S", 0.0)

    async def first():
        async for evt in mod.watch_devices():
            return evt

    evt = asyncio.run(asyncio.wait_for(first(), timeout=2.0))
    assert isinstance(evt, DeviceEvent)
    assert evt.path == "COM3"
    assert evt.vid == "1a86"
