"""macOS device watcher. ioreg + pyserial polling, 1.5s tick."""

from __future__ import annotations

import asyncio
import subprocess
from datetime import datetime, timezone
from typing import AsyncIterator

from robot_md.hotplug.event import DeviceEvent, classify_transport

_POLL_INTERVAL_S = 1.5


def _enumerate_macos() -> set[tuple]:
    """Return {(vid, pid, serial, path), ...} for currently-attached USB+serial devices."""
    out: set[tuple] = set()
    # Serial ports via pyserial.
    try:
        from serial.tools import list_ports
        for p in list_ports.comports():
            vid = f"{p.vid:04x}" if p.vid else None
            pid = f"{p.pid:04x}" if p.pid else None
            out.add((vid, pid, p.serial_number, p.device))
    except Exception:
        pass
    # USB devices via ioreg.
    try:
        result = subprocess.run(
            ["ioreg", "-p", "IOUSB", "-l", "-w", "0"],
            capture_output=True, text=True, timeout=5,
        )
        out.update(_parse_ioreg(result.stdout))
    except Exception:
        pass
    return out


def _parse_ioreg(text: str) -> set[tuple]:
    """Best-effort VID/PID/serial extraction from `ioreg -p IOUSB -l` output."""
    out: set[tuple] = set()
    blocks = text.split("+-o ")
    for block in blocks:
        vid = _extract(block, '"idVendor" = ')
        pid = _extract(block, '"idProduct" = ')
        serial = _extract(block, '"USB Serial Number" = "')
        if vid is not None and pid is not None:
            try:
                vid_hex = f"{int(vid):04x}"
                pid_hex = f"{int(pid):04x}"
            except ValueError:
                continue
            out.add((vid_hex, pid_hex, (serial.strip('"') if serial else None), ""))
    return out


def _extract(block: str, marker: str) -> str | None:
    idx = block.find(marker)
    if idx == -1:
        return None
    rest = block[idx + len(marker):]
    end = rest.find("\n")
    return (rest[:end] if end != -1 else rest).strip()


async def watch_devices() -> AsyncIterator[DeviceEvent]:
    seen = _enumerate_macos()
    while True:
        await asyncio.sleep(_POLL_INTERVAL_S)
        current = _enumerate_macos()
        new = current - seen
        seen = current
        for (vid, pid, serial, path) in new:
            yield DeviceEvent(
                kind="tty_added" if path else "usb_added",
                vid=vid,
                pid=pid,
                serial=serial,
                path=path,
                transport=classify_transport(vid=vid, pid=pid, subsystem=("tty" if path else "usb")),
                raw_metadata={},
                detected_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            )
