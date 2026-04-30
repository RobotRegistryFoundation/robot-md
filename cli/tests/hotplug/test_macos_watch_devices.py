from __future__ import annotations

import asyncio
import sys

import pytest

from robot_md.hotplug.event import DeviceEvent

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only")


def _fake_enumerate_first_call() -> set:
    return set()  # initial empty


def _fake_enumerate_second_call() -> set:
    return {("1a86", "7523", "AB12", "/dev/cu.usbmodem1234")}


def test_watch_devices_emits_new_devices_on_diff(monkeypatch) -> None:
    from robot_md.hotplug import macos as mod

    calls = iter([_fake_enumerate_first_call(), _fake_enumerate_second_call()])

    def fake_enum():
        return next(calls)

    monkeypatch.setattr(mod, "_enumerate_macos", fake_enum)
    # Drop the polling delay so the test runs fast.
    monkeypatch.setattr(mod, "_POLL_INTERVAL_S", 0.0)

    async def first():
        async for evt in mod.watch_devices():
            return evt

    evt = asyncio.run(asyncio.wait_for(first(), timeout=2.0))
    assert isinstance(evt, DeviceEvent)
    assert evt.vid == "1a86"
    assert evt.path == "/dev/cu.usbmodem1234"
