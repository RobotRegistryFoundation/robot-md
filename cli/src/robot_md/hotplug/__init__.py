"""Public API for the hot-plug daemon."""

from __future__ import annotations

from robot_md.hotplug.event import DeviceEvent, classify_transport

__all__ = ["DeviceEvent", "classify_transport"]
