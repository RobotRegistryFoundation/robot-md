from __future__ import annotations

import asyncio
import sys
import types
from unittest.mock import MagicMock

import pytest

from robot_md.hotplug.event import DeviceEvent


pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="linux-only")


def _install_fake_pyudev(monkeypatch, fake_events):
    """Stand up a fake pyudev module that yields the supplied (action, device) pairs."""
    fake = types.ModuleType("pyudev")

    class _Context: ...

    class _Monitor:
        @classmethod
        def from_netlink(cls, ctx):
            m = cls()
            m._events = list(fake_events)
            return m

        def filter_by(self, subsystem):
            return self

        def start(self):
            return self

        def __iter__(self):
            return iter(self._events)

    fake.Context = _Context
    fake.Monitor = _Monitor
    monkeypatch.setitem(sys.modules, "pyudev", fake)


def _make_fake_udev_device(*, vid="1a86", pid="7523", serial="AB12", subsystem="tty", path="/dev/ttyACM0"):
    dev = MagicMock()
    dev.subsystem = subsystem
    dev.device_node = path
    dev.get.side_effect = lambda key, default=None: {
        "ID_VENDOR_ID": vid,
        "ID_MODEL_ID": pid,
        "ID_SERIAL_SHORT": serial,
    }.get(key, default)
    return dev


def test_watch_devices_yields_device_event_on_add(monkeypatch) -> None:
    fake_dev = _make_fake_udev_device()
    _install_fake_pyudev(monkeypatch, [("add", fake_dev)])

    from robot_md.hotplug.linux import watch_devices

    async def first():
        async for evt in watch_devices():
            return evt
        return None

    evt = asyncio.run(first())
    assert isinstance(evt, DeviceEvent)
    assert evt.vid == "1a86"
    assert evt.pid == "7523"
    assert evt.transport == "feetech"
    assert evt.path == "/dev/ttyACM0"


def test_watch_devices_skips_remove_actions(monkeypatch) -> None:
    fake_remove = _make_fake_udev_device()
    fake_add = _make_fake_udev_device(path="/dev/ttyACM1")
    _install_fake_pyudev(monkeypatch, [("remove", fake_remove), ("add", fake_add)])

    from robot_md.hotplug.linux import watch_devices

    async def first():
        async for evt in watch_devices():
            return evt

    evt = asyncio.run(first())
    assert evt.path == "/dev/ttyACM1"  # remove was skipped
