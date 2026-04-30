from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

# VID:PID lookup table for known transports. Community-curated; expand via PR.
_TRANSPORT_TABLE: dict[tuple[str, str], str] = {
    ("1a86", "7523"): "feetech",  # CH340 — SO-ARM101, generic feetech bus
    ("0403", "6014"): "feetech",  # FTDI FT232H — alt feetech bus
    ("8086", "0b07"): "realsense",  # Intel RealSense D435
    ("8086", "0b3a"): "realsense",  # Intel RealSense D455
    ("03e7", "2485"): "uvc",  # Luxonis OAK-D
}


@dataclass(frozen=True)
class DeviceEvent:
    kind: Literal["usb_added", "tty_added"]
    vid: str | None
    pid: str | None
    serial: str | None
    path: str
    transport: Literal["feetech", "dynamixel", "realsense", "uvc", "unknown"]
    raw_metadata: dict[str, Any]
    detected_at: str  # ISO-8601 UTC


def classify_transport(*, vid: str | None, pid: str | None, subsystem: str) -> str:
    """Return a transport hint for a USB/tty device.

    Looks up VID:PID in the curated table; falls back to ``"unknown"``.
    Case-insensitive on VID/PID. Returns ``"unknown"`` if either is None.
    """
    if vid is None or pid is None:
        return "unknown"
    return _TRANSPORT_TABLE.get((vid.lower(), pid.lower()), "unknown")
