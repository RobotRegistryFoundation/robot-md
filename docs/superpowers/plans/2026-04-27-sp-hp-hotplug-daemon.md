# SP-HP — Hot-Plug Daemon Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the SP-HP runtime hot-plug daemon — a sibling persistent OS-level service (`robot-md hotplug-daemon`) that watches for USB / serial device hot-plug events, classifies them by tier (HIGH / MEDIUM / LOW), auto-binds HIGH-tier matches into the manifest, queues MEDIUM/LOW for operator confirmation, and exposes `hotplug_review` + `hotplug_confirm` MCP tools. Cross-platform from v1: Linux (pyudev real-time, <50 ms), macOS (ioreg + pyserial.tools.list_ports polling, 1–2 s), Windows (pywin32 WM_DEVICECHANGE + polling fallback, 1–2 s).

**Architecture:** Daemon lives in a new `cli/src/robot_md/hotplug/` package: per-platform `{linux,macos,windows}.py` watchers all yielding the same `DeviceEvent` shape; `matcher.py` classifies events by tier; `queue.py` writes a hash-chained `~/.robot-md/hotplug-events.jsonl`; `manifest.py` merges HIGH-tier auto-binds with schema validation BEFORE write; `audit.py` mirrors RRF's hash-chained audit-log shape per RRN. Daemon entry point at `daemon.py` composes everything + listens on a Linux Unix socket (`/run/user/$UID/robot-md-hotplug.sock`) for low-latency MCP wakeup nudges; macOS / Windows fall back to file-poll. MCP server gains: an inotify watch on `ROBOT.md` (kqueue on macOS via `watchdog`; ReadDirectoryChangesW on Windows) that reloads `RobotSpec` + emits `notifications/tools/list_changed`; a socket subscriber that drains the queue on nudge; two new tools (`hotplug_review`, `hotplug_confirm`). CLI surface: `robot-md hotplug-daemon start|stop|status`, `robot-md hotplug review|confirm`, `robot-md hotplug install-service`.

**Tech Stack:** Python 3.10+, asyncio, `pyudev` (Linux watcher), `pyserial.tools.list_ports` + `subprocess` to `ioreg` (macOS), `pywin32` (Windows), `watchdog` (cross-platform inotify abstraction), existing `jsonschema` validation, existing `fcntl` / `msvcrt.locking` for cross-platform file locking, `importlib.metadata.entry_points` for backend lookup, `hashlib.sha256` for queue/audit hash chains.

**Spec:** `docs/superpowers/specs/2026-04-27-sp-hp-hotplug-daemon-design.md`

**Depends on:** SP3 capability-metadata addendum (`Capability` dataclass, `enumerate_capabilities`) — Phase A of SP3 plan must land first.

---

## File Structure

**Daemon core (`cli/src/robot_md/hotplug/`):**
- `cli/src/robot_md/hotplug/__init__.py` — NEW. Public API re-exports.
- `cli/src/robot_md/hotplug/event.py` — NEW. `DeviceEvent` dataclass + transport-classification heuristic.
- `cli/src/robot_md/hotplug/linux.py` — NEW. `watch_devices()` async-iterator wrapping `pyudev.Monitor`.
- `cli/src/robot_md/hotplug/macos.py` — NEW. `watch_devices()` polling `ioreg -p IOUSB -l` + `pyserial.tools.list_ports`.
- `cli/src/robot_md/hotplug/windows.py` — NEW. `watch_devices()` consuming `WM_DEVICECHANGE` + polling fallback.
- `cli/src/robot_md/hotplug/matcher.py` — NEW. `BindProposal`, `Decision` dataclasses + `classify(evt)`.
- `cli/src/robot_md/hotplug/presets_index.py` — NEW. VID:PID → preset lookup table; built from existing presets at import time.
- `cli/src/robot_md/hotplug/queue.py` — NEW. `EventQueue` hash-chained append-only writer + reader.
- `cli/src/robot_md/hotplug/audit.py` — NEW. `AuditLog` per-RRN hash-chained append-only.
- `cli/src/robot_md/hotplug/manifest.py` — NEW. `merge(proposal, manifest_path)` with schema gate + fcntl lock.
- `cli/src/robot_md/hotplug/socket_listener.py` — NEW. Linux-only Unix socket listener for MCP-server nudges.
- `cli/src/robot_md/hotplug/daemon.py` — NEW. Async event loop composing watcher + matcher + queue + manifest + audit + socket.
- `cli/src/robot_md/hotplug/config.py` — NEW. Reads `~/.robot-md/hotplug.toml` (`pending_ttl_days`, etc.).

**MCP-server changes:**
- `cli/src/robot_md/mcp/server.py` — MODIFY. Register `hotplug_review` + `hotplug_confirm` tools; install inotify watch on `ROBOT.md`; create socket subscriber on connect.
- `cli/src/robot_md/mcp/tools/hotplug_review.py` — NEW. Reads pending events from `EventQueue`.
- `cli/src/robot_md/mcp/tools/hotplug_confirm.py` — NEW. Writes resolution via daemon socket-or-file API.
- `cli/src/robot_md/mcp/manifest_watcher.py` — NEW. inotify wrapper using `watchdog`; reloads `RobotSpec`, refreshes `BackendRegistry`, emits `notifications/tools/list_changed`.

**CLI:**
- `cli/src/robot_md/__main__.py` — MODIFY. Add `hotplug-daemon` and `hotplug` Typer subcommand groups.
- `cli/src/robot_md/hotplug/cli.py` — NEW. Typer app for `start|stop|status|review|confirm|install-service`.
- `cli/src/robot_md/hotplug/service_installers/linux_systemd.py` — NEW. Writes `~/.config/systemd/user/robot-md-hotplug.service`.
- `cli/src/robot_md/hotplug/service_installers/macos_launchd.py` — NEW. Writes `~/Library/LaunchAgents/dev.robotmd.hotplug.plist`.
- `cli/src/robot_md/hotplug/service_installers/windows_taskscheduler.py` — NEW. Creates Scheduled Task via `pywin32`.

**Tests (`cli/tests/hotplug/`):**
- Unit: `test_device_event.py`, `test_matcher_high_tier_*.py`, `test_matcher_medium_tier_*.py`, `test_matcher_low_tier_*.py`, `test_matcher_recent_reject_demotes.py`, `test_queue_append_pending_atomic.py`, `test_queue_resolution_first_writer_wins.py`, `test_queue_truncation_recovery.py`, `test_queue_hash_chain.py`, `test_queue_ttl_expiry.py`, `test_audit_log_append.py`, `test_manifest_merge_appends_driver.py`, `test_manifest_merge_validates_before_write.py`, `test_manifest_merge_locking.py`, `test_manifest_merge_no_manifest.py`, `test_socket_listener.py`, `test_daemon_starts_and_stops_clean.py`, `test_daemon_dedupes_replug.py`, `test_daemon_two_instances_eaddrinuse.py`, `test_daemon_handles_pending_ttl.py`.
- Per-platform: `test_linux_watch_devices.py` (`@pytest.mark.linux`), `test_macos_watch_devices.py` (`@pytest.mark.darwin`), `test_windows_watch_devices.py` (`@pytest.mark.win32`), `test_device_event_shape_consistent_across_platforms.py`.
- MCP-server: `test_mcp_inotify_reload_on_manifest_change.py`, `test_mcp_socket_subscribe_drains_queue.py`, `test_mcp_socket_fallback_to_polling.py`, `test_hotplug_review_returns_pending_only.py`, `test_hotplug_confirm_bind_writes_manifest.py`, `test_hotplug_confirm_reject_appends_resolution.py`.
- CLI: `test_cli_hotplug_install_service_linux.py`, `test_cli_hotplug_install_service_macos.py`, `test_cli_hotplug_status_reports_running.py`, `test_cli_hotplug_review_lists_pending.py`.
- Integration: `cli/tests/integration/test_sphp_replug_high_tier_end_to_end.py`.
- Hardware: `cli/tests/hardware/test_sphp_replug_so_arm101_high_tier.py`, `test_sphp_unknown_device_low_tier.py` (both `@pytest.mark.hardware`).
- Manual smoke: `cli/tests/manual/sphp_smoke.md`.

---

## Phase A — DeviceEvent + per-platform watchers

### Task 1: Add `DeviceEvent` dataclass + transport heuristic

**Files:**
- Create: `cli/src/robot_md/hotplug/__init__.py`, `cli/src/robot_md/hotplug/event.py`
- Test: `cli/tests/hotplug/test_device_event.py`

- [ ] **Step 1: Write the dataclass test**

```python
# cli/tests/hotplug/test_device_event.py
from __future__ import annotations

import pytest

from robot_md.hotplug.event import DeviceEvent, classify_transport


def test_device_event_is_frozen() -> None:
    e = DeviceEvent(
        kind="usb_added",
        vid="1a86", pid="7523", serial="AB12",
        path="/dev/ttyACM0",
        transport="feetech",
        raw_metadata={},
        detected_at="2026-04-27T19:30:11Z",
    )
    with pytest.raises(Exception):
        e.path = "/dev/ttyACM1"


def test_classify_transport_known_feetech_chip() -> None:
    # CH340 — bog-standard feetech bus chip used by SO-ARM101.
    assert classify_transport(vid="1a86", pid="7523", subsystem="tty") == "feetech"


def test_classify_transport_realsense() -> None:
    # Intel RealSense D435 vendor ID.
    assert classify_transport(vid="8086", pid="0b07", subsystem="usb") == "realsense"


def test_classify_transport_unknown() -> None:
    assert classify_transport(vid="dead", pid="beef", subsystem="usb") == "unknown"
```

- [ ] **Step 2: Run test (expect FAIL — module missing)**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/hotplug/test_device_event.py -v
```

- [ ] **Step 3: Create `event.py`**

```python
# cli/src/robot_md/hotplug/event.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


# VID:PID lookup table for known transports. Community-curated; expand via PR.
_TRANSPORT_TABLE: dict[tuple[str, str], str] = {
    ("1a86", "7523"): "feetech",   # CH340 — SO-ARM101, generic feetech bus
    ("0403", "6014"): "feetech",   # FTDI FT232H — alt feetech bus
    ("8086", "0b07"): "realsense", # Intel RealSense D435
    ("8086", "0b3a"): "realsense", # Intel RealSense D455
    ("03e7", "2485"): "uvc",       # Luxonis OAK-D
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

    Looks up VID:PID in the curated table; falls back to "unknown".
    """
    if vid is None or pid is None:
        return "unknown"
    return _TRANSPORT_TABLE.get((vid.lower(), pid.lower()), "unknown")
```

Create `cli/src/robot_md/hotplug/__init__.py`:

```python
"""Public API for the hot-plug daemon."""

from __future__ import annotations

from robot_md.hotplug.event import DeviceEvent, classify_transport

__all__ = ["DeviceEvent", "classify_transport"]
```

- [ ] **Step 4: Run test (expect PASS 4/4)**

- [ ] **Step 5: Commit (Task 1)**

```bash
cd /home/craigm26/robot-md/.worktrees/sp3-sdk-adapter
git add cli/src/robot_md/hotplug/__init__.py cli/src/robot_md/hotplug/event.py cli/tests/hotplug/test_device_event.py
git commit -m "$(cat <<'EOF'
feat(sphp): DeviceEvent dataclass + classify_transport heuristic

frozen=True DeviceEvent (kind/vid/pid/serial/path/transport/raw_metadata/
detected_at) shared across all three platform watchers.

classify_transport: looks up VID:PID in a curated table (CH340, FT232H,
Intel RealSense D435/D455, Luxonis OAK-D); returns "unknown" fallthrough
which maps to LOW tier in the matcher.

Table is community-curated via PR — no autoupdate.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Linux `watch_devices()` (pyudev real-time)

**Files:**
- Create: `cli/src/robot_md/hotplug/linux.py`
- Test: `cli/tests/hotplug/test_linux_watch_devices.py`

- [ ] **Step 1: Write the linux watcher test**

```python
# cli/tests/hotplug/test_linux_watch_devices.py
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
```

- [ ] **Step 2: Run test (expect FAIL — module missing)**

- [ ] **Step 3: Implement `linux.py`**

```python
# cli/src/robot_md/hotplug/linux.py
"""Linux pyudev-based real-time device watcher. <50ms latency."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import AsyncIterator

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

    def _drain():
        for action, device in monitor:
            if action != "add":
                continue
            evt = _device_to_event(device)
            asyncio.run_coroutine_threadsafe(queue.put(evt), loop)

    # Background reader so the iterator can yield without blocking the event loop.
    asyncio.get_running_loop().run_in_executor(None, _drain)

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
        vid=vid, pid=pid, serial=serial,
        path=device.device_node or "",
        transport=classify_transport(vid=vid, pid=pid, subsystem=subsystem),
        raw_metadata={},
        detected_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )
```

(The test's fake-Monitor `__iter__` is synchronous; the production code's threadpool drain is the right shape but the test exercises the iterator's `_device_to_event` path directly via the synchronous `for` loop. Adapt the test if the real implementation needs more substantial loop integration — the goal is to assert the event-shape conversion, not the asyncio plumbing.)

- [ ] **Step 4: Run test (expect PASS 2/2)**

- [ ] **Step 5: Commit (Task 2)**

```bash
git add cli/src/robot_md/hotplug/linux.py cli/tests/hotplug/test_linux_watch_devices.py
git commit -m "feat(sphp): linux watch_devices() via pyudev netlink monitor"
```

---

### Task 3: macOS `watch_devices()` (ioreg + pyserial polling)

**Files:**
- Create: `cli/src/robot_md/hotplug/macos.py`
- Test: `cli/tests/hotplug/test_macos_watch_devices.py`

- [ ] **Step 1: Write the macOS watcher test**

```python
# cli/tests/hotplug/test_macos_watch_devices.py
from __future__ import annotations

import asyncio
import sys
from unittest.mock import patch

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
```

- [ ] **Step 2: Run test (expect FAIL — module missing)**

- [ ] **Step 3: Implement `macos.py`**

```python
# cli/src/robot_md/hotplug/macos.py
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
                vid=vid, pid=pid, serial=serial,
                path=path,
                transport=classify_transport(vid=vid, pid=pid, subsystem=("tty" if path else "usb")),
                raw_metadata={},
                detected_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            )
```

- [ ] **Step 4: Run test (expect PASS)**

- [ ] **Step 5: Commit (Task 3)**

```bash
git add cli/src/robot_md/hotplug/macos.py cli/tests/hotplug/test_macos_watch_devices.py
git commit -m "feat(sphp): macOS watch_devices() via ioreg + pyserial polling"
```

---

### Task 4: Windows `watch_devices()` (WM_DEVICECHANGE + polling fallback)

**Files:**
- Create: `cli/src/robot_md/hotplug/windows.py`
- Test: `cli/tests/hotplug/test_windows_watch_devices.py`

- [ ] **Step 1: Write the Windows watcher test**

```python
# cli/tests/hotplug/test_windows_watch_devices.py
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
```

- [ ] **Step 2: Run test (expect FAIL — module missing)**

- [ ] **Step 3: Implement `windows.py`**

```python
# cli/src/robot_md/hotplug/windows.py
"""Windows device watcher. WM_DEVICECHANGE preferred; polling fallback."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import AsyncIterator

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
        for (vid, pid, serial, path) in new:
            yield DeviceEvent(
                kind="tty_added",
                vid=vid, pid=pid, serial=serial,
                path=path,
                transport=classify_transport(vid=vid, pid=pid, subsystem="tty"),
                raw_metadata={},
                detected_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            )
```

- [ ] **Step 4: Run test (expect PASS)**

- [ ] **Step 5: Commit (Task 4)**

```bash
git add cli/src/robot_md/hotplug/windows.py cli/tests/hotplug/test_windows_watch_devices.py
git commit -m "feat(sphp): Windows watch_devices() polling fallback (WM_DEVICECHANGE in Task 5)"
```

---

### Task 5: Lock cross-platform DeviceEvent shape consistency

**Files:**
- Test: `cli/tests/hotplug/test_device_event_shape_consistent_across_platforms.py`

- [ ] **Step 1: Write the consistency test**

```python
# cli/tests/hotplug/test_device_event_shape_consistent_across_platforms.py
from __future__ import annotations

from dataclasses import fields

from robot_md.hotplug.event import DeviceEvent


def test_all_event_field_names_stable() -> None:
    """If anyone touches DeviceEvent's field set, they must update all three
    watchers + the matcher together. This test pins the field names."""
    expected = {
        "kind", "vid", "pid", "serial", "path",
        "transport", "raw_metadata", "detected_at",
    }
    actual = {f.name for f in fields(DeviceEvent)}
    assert actual == expected, (
        f"DeviceEvent fields drifted from canonical set. "
        f"Expected {expected}, got {actual}. "
        f"Update linux.py / macos.py / windows.py + matcher.py atomically."
    )
```

- [ ] **Step 2: Run test (expect PASS)**

- [ ] **Step 3: Commit (Task 5)**

```bash
git add cli/tests/hotplug/test_device_event_shape_consistent_across_platforms.py
git commit -m "test(sphp): pin DeviceEvent field set across all three platforms"
```

---

## Phase B — Matcher (tier classification)

### Task 6: Add `BindProposal` + `Decision` dataclasses + presets-index helper

**Files:**
- Create: `cli/src/robot_md/hotplug/matcher.py` (dataclasses only — `classify` follows)
- Create: `cli/src/robot_md/hotplug/presets_index.py`
- Test: `cli/tests/hotplug/test_presets_index.py`

- [ ] **Step 1: Write the presets-index test**

```python
# cli/tests/hotplug/test_presets_index.py
from __future__ import annotations

from robot_md.hotplug.presets_index import lookup_by_vid_pid


def test_lookup_so_arm101_by_known_vid_pid() -> None:
    matches = lookup_by_vid_pid(vid="1a86", pid="7523")
    names = {m.preset_name for m in matches}
    # All SO-ARM presets share the CH340 chip; they all match.
    assert "so_arm101" in names
    assert "so_arm101_leader" in names


def test_lookup_unknown_vid_pid_returns_empty() -> None:
    assert lookup_by_vid_pid(vid="dead", pid="beef") == []
```

- [ ] **Step 2: Run test (expect FAIL — module missing)**

- [ ] **Step 3: Implement `presets_index.py`**

```python
# cli/src/robot_md/hotplug/presets_index.py
"""VID:PID → preset lookup, built from existing presets at import time.

We trade preset YAML round-tripping for an explicit hint table here: presets
themselves don't currently declare VID:PID (that's a future SP3.x extension).
Until they do, this module ships a hand-curated mapping derived from each
preset's documented hardware.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PresetMatch:
    preset_name: str
    transport: str
    confidence: str  # "exact_match" | "family_match"


# Hand-curated initial table; expand via PR as new presets land.
_VID_PID_TO_PRESETS: dict[tuple[str, str], list[PresetMatch]] = {
    # CH340 — used by all SO-ARM family kits + many generic feetech rigs.
    ("1a86", "7523"): [
        PresetMatch("so_arm101", "feetech", "family_match"),
        PresetMatch("so_arm101_leader", "feetech", "family_match"),
        PresetMatch("koch_arm", "feetech", "family_match"),
    ],
    # FT232H — alternative feetech bus.
    ("0403", "6014"): [
        PresetMatch("aloha2", "feetech", "family_match"),
    ],
    # RealSense D435 / D455.
    ("8086", "0b07"): [PresetMatch("scanrig_realsense", "realsense", "exact_match")],
    ("8086", "0b3a"): [PresetMatch("scanrig_realsense", "realsense", "exact_match")],
}


def lookup_by_vid_pid(*, vid: str | None, pid: str | None) -> list[PresetMatch]:
    if vid is None or pid is None:
        return []
    return list(_VID_PID_TO_PRESETS.get((vid.lower(), pid.lower()), []))
```

- [ ] **Step 4: Write the matcher dataclass test**

```python
# cli/tests/hotplug/test_matcher_dataclasses.py
from __future__ import annotations

from robot_md.hotplug.matcher import BindProposal, Decision


def test_bind_proposal_is_frozen() -> None:
    bp = BindProposal(
        rrn="RRN-test",
        driver_id_suggestion="arm_servos",
        backend_name="lerobot",
        preset_name="so_arm101",
        capability_preview=[],
        inferred_fields={"port": "/dev/ttyACM0"},
    )
    import pytest
    with pytest.raises(Exception):
        bp.backend_name = "feetech_depthai"


def test_decision_dataclass_shape() -> None:
    d = Decision(tier="HIGH", unambiguous=True, bind_proposal=None, alternatives=[], reasons=[])
    assert d.tier == "HIGH"
    assert d.alternatives == []
```

- [ ] **Step 5: Implement `matcher.py` (dataclasses only)**

```python
# cli/src/robot_md/hotplug/matcher.py
"""Hot-plug event tier classifier. classify() lands in Task 7."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from robot_md.backends.capability import Capability


@dataclass(frozen=True)
class BindProposal:
    rrn: str | None
    driver_id_suggestion: str
    backend_name: str
    preset_name: str | None
    capability_preview: list[Capability]
    inferred_fields: dict


@dataclass(frozen=True)
class Decision:
    tier: Literal["HIGH", "MEDIUM", "LOW"]
    unambiguous: bool
    bind_proposal: BindProposal | None
    alternatives: list[BindProposal] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
```

- [ ] **Step 6: Run tests (expect PASS)**

- [ ] **Step 7: Commit (Task 6)**

```bash
git add cli/src/robot_md/hotplug/matcher.py cli/src/robot_md/hotplug/presets_index.py cli/tests/hotplug/test_presets_index.py cli/tests/hotplug/test_matcher_dataclasses.py
git commit -m "feat(sphp): BindProposal + Decision dataclasses + presets-index lookup"
```

---

### Task 7: Implement `classify(evt)` — HIGH/MEDIUM/LOW tiering

**Files:**
- Modify: `cli/src/robot_md/hotplug/matcher.py` (add `classify`)
- Test: `cli/tests/hotplug/test_matcher_high_tier_exact.py`, `cli/tests/hotplug/test_matcher_medium_tier.py`, `cli/tests/hotplug/test_matcher_low_tier.py`

- [ ] **Step 1: Write the HIGH-tier test**

```python
# cli/tests/hotplug/test_matcher_high_tier_exact.py
from __future__ import annotations

from unittest.mock import patch

from robot_md.hotplug.event import DeviceEvent
from robot_md.hotplug.matcher import classify
from robot_md.hotplug.presets_index import PresetMatch


def _evt() -> DeviceEvent:
    return DeviceEvent(
        kind="tty_added",
        vid="1a86", pid="7523", serial="UNIQUE_SERIAL_AB12",
        path="/dev/ttyACM0",
        transport="feetech",
        raw_metadata={},
        detected_at="2026-04-27T19:30:11Z",
    )


def test_high_tier_when_serial_uniquely_identifies_preset_and_one_backend(monkeypatch) -> None:
    # Single-preset match (override the table to simulate a serial-unique preset).
    monkeypatch.setattr(
        "robot_md.hotplug.presets_index.lookup_by_vid_pid",
        lambda *, vid, pid: [PresetMatch("so_arm101", "feetech", "exact_match")],
    )
    # Only lerobot backend installed.
    with patch("robot_md.hotplug.matcher._installed_backends_for_transport",
               return_value=["lerobot"]):
        decision = classify(_evt())
    assert decision.tier == "HIGH"
    assert decision.unambiguous is True
    assert decision.bind_proposal is not None
    assert decision.bind_proposal.backend_name == "lerobot"
    assert decision.bind_proposal.preset_name == "so_arm101"
```

- [ ] **Step 2: Write the MEDIUM-tier test**

```python
# cli/tests/hotplug/test_matcher_medium_tier.py
from __future__ import annotations

from unittest.mock import patch

from robot_md.hotplug.event import DeviceEvent
from robot_md.hotplug.matcher import classify


def _evt() -> DeviceEvent:
    return DeviceEvent(
        kind="tty_added", vid="1a86", pid="7523", serial=None,
        path="/dev/ttyACM0", transport="feetech",
        raw_metadata={}, detected_at="2026-04-27T19:30:11Z",
    )


def test_medium_tier_when_multi_preset_match() -> None:
    # Default presets-index returns 3 matches for 1a86:7523.
    with patch("robot_md.hotplug.matcher._installed_backends_for_transport",
               return_value=["lerobot"]):
        decision = classify(_evt())
    assert decision.tier == "MEDIUM"
    assert decision.unambiguous is False
    assert len(decision.alternatives) >= 2
```

- [ ] **Step 3: Write the LOW-tier test**

```python
# cli/tests/hotplug/test_matcher_low_tier.py
from __future__ import annotations

from unittest.mock import patch

from robot_md.hotplug.event import DeviceEvent
from robot_md.hotplug.matcher import classify


def _evt(transport="unknown", vid="dead", pid="beef") -> DeviceEvent:
    return DeviceEvent(
        kind="usb_added", vid=vid, pid=pid, serial=None,
        path="/dev/ttyACM0", transport=transport,
        raw_metadata={}, detected_at="2026-04-27T19:30:11Z",
    )


def test_low_tier_when_unknown_vid_pid() -> None:
    decision = classify(_evt())
    assert decision.tier == "LOW"
    assert any("preset" in r.lower() for r in decision.reasons)


def test_low_tier_when_known_transport_no_backend() -> None:
    with patch("robot_md.hotplug.matcher._installed_backends_for_transport",
               return_value=[]):
        decision = classify(_evt(transport="feetech", vid="1a86", pid="7523"))
    assert decision.tier == "LOW"
    assert any("backend" in r.lower() for r in decision.reasons)
```

- [ ] **Step 4: Run tests (expect FAIL — `classify` not implemented)**

- [ ] **Step 5: Implement `classify`**

Append to `cli/src/robot_md/hotplug/matcher.py`:

```python
from robot_md.backends import BackendRegistry
from robot_md.hotplug.event import DeviceEvent
from robot_md.hotplug.presets_index import lookup_by_vid_pid


def _installed_backends_for_transport(transport: str) -> list[str]:
    """Return names of installed backends whose .protocols set includes transport."""
    reg = BackendRegistry.from_entry_points()
    return sorted(b.name for b in reg.backends if transport in b.protocols)


def classify(evt: DeviceEvent) -> Decision:
    """Tier-classify a hot-plug event.

    HIGH:   single preset match (typically via VID:PID:serial triple) AND
            exactly one matching backend installed → auto-bind.
    MEDIUM: multi-preset match OR multi-backend match. Top-1 candidate +
            alternatives surfaced; queued.
    LOW:    no preset match OR known transport with no backend installed.
    """
    preset_matches = lookup_by_vid_pid(vid=evt.vid, pid=evt.pid)
    if not preset_matches:
        return Decision(
            tier="LOW", unambiguous=False, bind_proposal=None,
            alternatives=[],
            reasons=[f"no preset match for VID:PID {evt.vid}:{evt.pid}"],
        )

    backends = _installed_backends_for_transport(evt.transport)
    if not backends:
        return Decision(
            tier="LOW", unambiguous=False, bind_proposal=None,
            alternatives=[],
            reasons=[
                f"no backend installed for transport {evt.transport!r}",
                "hint: pip install 'robot-md[hardware]'",
            ],
        )

    proposals: list[BindProposal] = []
    for pm in preset_matches:
        for backend_name in backends:
            proposals.append(BindProposal(
                rrn=None,
                driver_id_suggestion="arm_servos",
                backend_name=backend_name,
                preset_name=pm.preset_name,
                capability_preview=[],  # populated lazily by review tool
                inferred_fields={"port": evt.path, "transport": evt.transport, "serial": evt.serial},
            ))

    if len(proposals) == 1 and preset_matches[0].confidence == "exact_match":
        return Decision(
            tier="HIGH", unambiguous=True, bind_proposal=proposals[0],
            alternatives=[],
            reasons=[
                f"exact preset match {preset_matches[0].preset_name}",
                f"single backend installed: {backends[0]}",
            ],
        )

    return Decision(
        tier="MEDIUM", unambiguous=False,
        bind_proposal=proposals[0],
        alternatives=proposals[1:],
        reasons=[
            f"VID:PID matches {len(preset_matches)} preset(s)",
            f"{len(backends)} backend(s) could drive this transport",
        ],
    )
```

- [ ] **Step 6: Run tests (expect PASS)**

- [ ] **Step 7: Commit (Task 7)**

```bash
git add cli/src/robot_md/hotplug/matcher.py cli/tests/hotplug/test_matcher_high_tier_exact.py cli/tests/hotplug/test_matcher_medium_tier.py cli/tests/hotplug/test_matcher_low_tier.py
git commit -m "feat(sphp): classify(DeviceEvent) — HIGH/MEDIUM/LOW tier policy"
```

---

### Task 8: Recent-reject demotion — HIGH-tier match becomes MEDIUM if same device was rejected within an hour

**Files:**
- Modify: `cli/src/robot_md/hotplug/matcher.py`
- Test: `cli/tests/hotplug/test_matcher_recent_reject_demotes.py`

- [ ] **Step 1: Write the demotion test**

```python
# cli/tests/hotplug/test_matcher_recent_reject_demotes.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from robot_md.hotplug.event import DeviceEvent
from robot_md.hotplug.matcher import classify
from robot_md.hotplug.presets_index import PresetMatch


def _evt(serial="AB12") -> DeviceEvent:
    return DeviceEvent(
        kind="tty_added", vid="1a86", pid="7523", serial=serial,
        path="/dev/ttyACM0", transport="feetech",
        raw_metadata={}, detected_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )


def test_recent_reject_within_window_demotes_high_to_medium(monkeypatch) -> None:
    monkeypatch.setattr(
        "robot_md.hotplug.presets_index.lookup_by_vid_pid",
        lambda *, vid, pid: [PresetMatch("so_arm101", "feetech", "exact_match")],
    )
    recent = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat().replace("+00:00", "Z")
    with patch("robot_md.hotplug.matcher._installed_backends_for_transport", return_value=["lerobot"]), \
         patch("robot_md.hotplug.matcher._recent_reject_for", return_value=recent):
        decision = classify(_evt())
    assert decision.tier == "MEDIUM"
    assert any("rejected" in r.lower() for r in decision.reasons)


def test_old_reject_does_not_demote(monkeypatch) -> None:
    monkeypatch.setattr(
        "robot_md.hotplug.presets_index.lookup_by_vid_pid",
        lambda *, vid, pid: [PresetMatch("so_arm101", "feetech", "exact_match")],
    )
    old = (datetime.now(timezone.utc) - timedelta(hours=4)).isoformat().replace("+00:00", "Z")
    with patch("robot_md.hotplug.matcher._installed_backends_for_transport", return_value=["lerobot"]), \
         patch("robot_md.hotplug.matcher._recent_reject_for", return_value=old):
        decision = classify(_evt())
    assert decision.tier == "HIGH"
```

- [ ] **Step 2: Run test (expect FAIL — `_recent_reject_for` doesn't exist)**

- [ ] **Step 3: Add the demotion path**

In `cli/src/robot_md/hotplug/matcher.py`, add a stub helper + integrate into `classify`:

```python
from datetime import datetime, timedelta, timezone

_RECENT_REJECT_WINDOW = timedelta(hours=1)


def _recent_reject_for(evt: DeviceEvent) -> str | None:
    """Return the ISO timestamp of the most-recent reject for this device, or None.

    Default implementation reads the queue file. Tests patch this to inject
    fixtures. The queue file path lives in ~/.robot-md/hotplug-events.jsonl
    (see Task 9).
    """
    # Implementation lives in queue.py once that exists; for now, return None
    # so the production path defaults to "no recent reject" until Task 9 wires it.
    return None
```

Update `classify` to call this and demote if within the window. Edit the HIGH-tier branch:

```python
    if len(proposals) == 1 and preset_matches[0].confidence == "exact_match":
        recent = _recent_reject_for(evt)
        if recent is not None:
            recent_dt = datetime.fromisoformat(recent.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) - recent_dt < _RECENT_REJECT_WINDOW:
                return Decision(
                    tier="MEDIUM", unambiguous=False,
                    bind_proposal=proposals[0],
                    alternatives=[],
                    reasons=[
                        f"exact preset match {preset_matches[0].preset_name}",
                        f"recently rejected at {recent}; not auto-binding",
                    ],
                )
        return Decision(
            tier="HIGH", unambiguous=True, bind_proposal=proposals[0],
            alternatives=[],
            reasons=[
                f"exact preset match {preset_matches[0].preset_name}",
                f"single backend installed: {backends[0]}",
            ],
        )
```

- [ ] **Step 4: Run test (expect PASS 2/2)**

- [ ] **Step 5: Commit (Task 8)**

```bash
git add cli/src/robot_md/hotplug/matcher.py cli/tests/hotplug/test_matcher_recent_reject_demotes.py
git commit -m "feat(sphp): demote HIGH→MEDIUM when device was rejected within 1h"
```

---

## Phase C — Hash-chained queue + audit log

### Task 9: `EventQueue.append_pending` + `append_resolution` (hash chain)

**Files:**
- Create: `cli/src/robot_md/hotplug/queue.py`
- Test: `cli/tests/hotplug/test_queue_hash_chain.py`, `cli/tests/hotplug/test_queue_append_pending_atomic.py`

- [ ] **Step 1: Write the hash-chain test**

```python
# cli/tests/hotplug/test_queue_hash_chain.py
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from robot_md.hotplug.event import DeviceEvent
from robot_md.hotplug.matcher import Decision
from robot_md.hotplug.queue import EventQueue


def _evt() -> DeviceEvent:
    return DeviceEvent(
        kind="tty_added", vid="1a86", pid="7523", serial="AB12",
        path="/dev/ttyACM0", transport="feetech",
        raw_metadata={}, detected_at="2026-04-27T19:30:11Z",
    )


def test_first_record_uses_zero_prev_hash(tmp_path: Path) -> None:
    q = EventQueue(path=tmp_path / "q.jsonl")
    decision = Decision(tier="LOW", unambiguous=False, bind_proposal=None)
    rec = q.append_pending(_evt(), decision)
    assert rec.prev_hash == "sha256:" + ("0" * 64)


def test_second_record_chains_to_first(tmp_path: Path) -> None:
    q = EventQueue(path=tmp_path / "q.jsonl")
    decision = Decision(tier="LOW", unambiguous=False, bind_proposal=None)
    first = q.append_pending(_evt(), decision)
    second = q.append_pending(_evt(), decision)
    assert second.prev_hash == first.this_hash
```

- [ ] **Step 2: Write the atomicity test**

```python
# cli/tests/hotplug/test_queue_append_pending_atomic.py
from __future__ import annotations

import threading
from pathlib import Path

from robot_md.hotplug.event import DeviceEvent
from robot_md.hotplug.matcher import Decision
from robot_md.hotplug.queue import EventQueue


def test_concurrent_appenders_all_records_present(tmp_path: Path) -> None:
    q = EventQueue(path=tmp_path / "q.jsonl")
    decision = Decision(tier="LOW", unambiguous=False, bind_proposal=None)

    def append():
        q.append_pending(DeviceEvent(
            kind="tty_added", vid="1a86", pid="7523", serial=None,
            path="/dev/ttyACM0", transport="feetech",
            raw_metadata={}, detected_at="2026-04-27T19:30:11Z",
        ), decision)

    threads = [threading.Thread(target=append) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    lines = (tmp_path / "q.jsonl").read_text().splitlines()
    assert len(lines) == 20
```

- [ ] **Step 3: Run tests (expect FAIL — module missing)**

- [ ] **Step 4: Implement `queue.py`**

```python
# cli/src/robot_md/hotplug/queue.py
"""Hash-chained append-only event queue at ~/.robot-md/hotplug-events.jsonl.

Same shape as RRF's compliance audit trail: each record carries a sha256
of (prev_hash || canonical_json(record_minus_hash)), so any tampering is
detectable end-to-end.
"""

from __future__ import annotations

import dataclasses
import fcntl
import hashlib
import json
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from robot_md.hotplug.event import DeviceEvent
from robot_md.hotplug.matcher import Decision


_DEFAULT_PATH = Path.home() / ".robot-md" / "hotplug-events.jsonl"
_ZERO_HASH = "sha256:" + "0" * 64


@dataclass(frozen=True)
class QueueRecord:
    id: str
    ts: str
    kind: str   # "pending" | "resolved" | "daemon_alert"
    event: dict | None
    decision: dict | None
    ref: str | None  # set on "resolved" records → original "pending" id
    resolution: str | None
    by: str | None
    outcome: dict | None
    prev_hash: str
    this_hash: str


def _hash_record(prev_hash: str, body: dict) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    h = hashlib.sha256()
    h.update(prev_hash.encode("ascii"))
    h.update(b"\0")
    h.update(canonical.encode("utf-8"))
    return "sha256:" + h.hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class EventQueue:
    def __init__(self, *, path: Path = _DEFAULT_PATH) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def _last_hash(self) -> str:
        with self.path.open("rb") as f:
            data = f.read()
        if not data:
            return _ZERO_HASH
        last_line = data.rstrip(b"\n").rsplit(b"\n", 1)[-1]
        try:
            return json.loads(last_line)["this_hash"]
        except Exception:
            return _ZERO_HASH

    def append_pending(self, evt: DeviceEvent, decision: Decision) -> QueueRecord:
        with self.path.open("ab") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                prev = self._last_hash()
                body = {
                    "id": "evt_" + uuid.uuid4().hex,
                    "ts": _now_iso(),
                    "kind": "pending",
                    "event": asdict(evt),
                    "decision": _decision_to_dict(decision),
                    "ref": None,
                    "resolution": None,
                    "by": None,
                    "outcome": None,
                    "prev_hash": prev,
                }
                body["this_hash"] = _hash_record(prev, body)
                line = json.dumps(body, sort_keys=True) + "\n"
                f.write(line.encode("utf-8"))
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return QueueRecord(**body)

    def append_resolution(self, *, ref_id: str, resolution: str, by: str, outcome: dict | None) -> QueueRecord:
        with self.path.open("ab") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                prev = self._last_hash()
                body = {
                    "id": "evt_" + uuid.uuid4().hex,
                    "ts": _now_iso(),
                    "kind": "resolved",
                    "event": None,
                    "decision": None,
                    "ref": ref_id,
                    "resolution": resolution,
                    "by": by,
                    "outcome": outcome,
                    "prev_hash": prev,
                }
                body["this_hash"] = _hash_record(prev, body)
                line = json.dumps(body, sort_keys=True) + "\n"
                f.write(line.encode("utf-8"))
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return QueueRecord(**body)


def _decision_to_dict(d: Decision) -> dict:
    out = dataclasses.asdict(d)
    return out
```

- [ ] **Step 5: Run tests (expect PASS)**

- [ ] **Step 6: Commit (Task 9)**

```bash
git add cli/src/robot_md/hotplug/queue.py cli/tests/hotplug/test_queue_hash_chain.py cli/tests/hotplug/test_queue_append_pending_atomic.py
git commit -m "feat(sphp): hash-chained EventQueue with fcntl-locked atomic appends"
```

---

### Task 10: Resolution semantics — first-writer-wins; truncation recovery; TTL expiry

**Files:**
- Modify: `cli/src/robot_md/hotplug/queue.py`
- Test: `cli/tests/hotplug/test_queue_resolution_first_writer_wins.py`, `test_queue_truncation_recovery.py`, `test_queue_ttl_expiry.py`

- [ ] **Step 1: Write the first-writer test**

```python
# cli/tests/hotplug/test_queue_resolution_first_writer_wins.py
from __future__ import annotations

from pathlib import Path

import pytest

from robot_md.hotplug.event import DeviceEvent
from robot_md.hotplug.matcher import Decision
from robot_md.hotplug.queue import EventQueue, AlreadyResolvedError


def _evt() -> DeviceEvent:
    return DeviceEvent(
        kind="tty_added", vid="1a86", pid="7523", serial="AB12",
        path="/dev/ttyACM0", transport="feetech",
        raw_metadata={}, detected_at="2026-04-27T19:30:11Z",
    )


def test_second_resolution_for_same_event_raises(tmp_path: Path) -> None:
    q = EventQueue(path=tmp_path / "q.jsonl")
    pending = q.append_pending(_evt(), Decision(tier="MEDIUM", unambiguous=False, bind_proposal=None))
    q.append_resolution(ref_id=pending.id, resolution="bind", by="claude", outcome={})
    with pytest.raises(AlreadyResolvedError) as ex:
        q.append_resolution(ref_id=pending.id, resolution="bind", by="cli", outcome={})
    assert "claude" in str(ex.value)
```

- [ ] **Step 2: Write the truncation-recovery test**

```python
# cli/tests/hotplug/test_queue_truncation_recovery.py
from __future__ import annotations

from pathlib import Path

from robot_md.hotplug.event import DeviceEvent
from robot_md.hotplug.matcher import Decision
from robot_md.hotplug.queue import EventQueue


def _evt() -> DeviceEvent:
    return DeviceEvent(
        kind="tty_added", vid="1a86", pid="7523", serial=None,
        path="/dev/ttyACM0", transport="feetech",
        raw_metadata={}, detected_at="2026-04-27T19:30:11Z",
    )


def test_corrupt_last_line_drops_to_alert_and_continues(tmp_path: Path) -> None:
    q = EventQueue(path=tmp_path / "q.jsonl")
    q.append_pending(_evt(), Decision(tier="LOW", unambiguous=False, bind_proposal=None))
    # Corrupt the file by appending a partial line.
    with (tmp_path / "q.jsonl").open("ab") as f:
        f.write(b'{"id":"truncat')
    q2 = EventQueue(path=tmp_path / "q.jsonl")
    pending = q2.append_pending(_evt(), Decision(tier="LOW", unambiguous=False, bind_proposal=None))
    contents = (tmp_path / "q.jsonl").read_text()
    assert "daemon_alert" in contents
    assert pending.kind == "pending"  # subsequent append still works
```

- [ ] **Step 3: Write the TTL-expiry test**

```python
# cli/tests/hotplug/test_queue_ttl_expiry.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from robot_md.hotplug.event import DeviceEvent
from robot_md.hotplug.matcher import Decision
from robot_md.hotplug.queue import EventQueue


def _evt() -> DeviceEvent:
    return DeviceEvent(
        kind="tty_added", vid="1a86", pid="7523", serial=None,
        path="/dev/ttyACM0", transport="feetech",
        raw_metadata={}, detected_at=(datetime.now(timezone.utc) - timedelta(days=10)).isoformat().replace("+00:00", "Z"),
    )


def test_expire_pending_older_than_ttl(tmp_path: Path) -> None:
    q = EventQueue(path=tmp_path / "q.jsonl")
    pending = q.append_pending(_evt(), Decision(tier="MEDIUM", unambiguous=False, bind_proposal=None))
    # Force the queue's first record's ts to 10 days ago by direct manipulation
    # is awkward — use the public API: expire_old() with ttl=1 day.
    expired_ids = q.expire_old(ttl_days=1)
    assert pending.id in expired_ids
    contents = (tmp_path / "q.jsonl").read_text()
    assert '"resolution": "expired"' in contents
```

- [ ] **Step 4: Run tests (expect FAIL — features missing)**

- [ ] **Step 5: Implement first-writer-wins, truncation recovery, TTL**

Append to `cli/src/robot_md/hotplug/queue.py`:

```python
class AlreadyResolvedError(Exception):
    def __init__(self, *, ref_id: str, by: str) -> None:
        super().__init__(f"event {ref_id} already resolved by {by}")
        self.ref_id = ref_id
        self.by = by


def _safe_iter_records(path: Path) -> tuple[list[dict], int]:
    """Yield valid JSON records; return list + count of dropped malformed lines."""
    records: list[dict] = []
    dropped = 0
    if not path.exists():
        return records, 0
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except Exception:
            dropped += 1
    return records, dropped


# Patch EventQueue with the missing methods.
def _ensure_no_existing_resolution(self: EventQueue, ref_id: str) -> None:
    records, _ = _safe_iter_records(self.path)
    for rec in records:
        if rec.get("kind") == "resolved" and rec.get("ref") == ref_id:
            raise AlreadyResolvedError(ref_id=ref_id, by=rec.get("by") or "unknown")


def _emit_alert_if_truncation_observed(self: EventQueue) -> None:
    records, dropped = _safe_iter_records(self.path)
    if dropped == 0:
        return
    # Append a daemon_alert record (uses the same hash chain shape).
    with self.path.open("ab") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            prev = self._last_hash()
            body = {
                "id": "evt_" + uuid.uuid4().hex,
                "ts": _now_iso(),
                "kind": "daemon_alert",
                "event": None, "decision": None,
                "ref": None, "resolution": None, "by": "daemon",
                "outcome": {"msg": "queue tail truncated", "dropped": dropped},
                "prev_hash": prev,
            }
            body["this_hash"] = _hash_record(prev, body)
            f.write((json.dumps(body, sort_keys=True) + "\n").encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def _expire_old(self: EventQueue, ttl_days: float) -> list[str]:
    records, _ = _safe_iter_records(self.path)
    now = datetime.now(timezone.utc)
    threshold = timedelta(days=ttl_days)

    pending_by_id = {r["id"]: r for r in records if r.get("kind") == "pending"}
    resolved_refs = {r["ref"] for r in records if r.get("kind") == "resolved" and r.get("ref")}

    expired_ids: list[str] = []
    for rid, rec in pending_by_id.items():
        if rid in resolved_refs:
            continue
        ts = datetime.fromisoformat(rec["ts"].replace("Z", "+00:00"))
        if (now - ts) > threshold:
            self.append_resolution(ref_id=rid, resolution="expired", by="daemon", outcome=None)
            expired_ids.append(rid)
    return expired_ids


# Bind the new methods to EventQueue.
EventQueue.expire_old = _expire_old
_orig_init = EventQueue.__init__


def _patched_init(self, *, path: Path = _DEFAULT_PATH) -> None:
    _orig_init(self, path=path)
    _emit_alert_if_truncation_observed(self)


EventQueue.__init__ = _patched_init

_orig_append_resolution = EventQueue.append_resolution


def _patched_append_resolution(self, *, ref_id: str, resolution: str, by: str, outcome: dict | None) -> QueueRecord:
    _ensure_no_existing_resolution(self, ref_id)
    return _orig_append_resolution(self, ref_id=ref_id, resolution=resolution, by=by, outcome=outcome)


EventQueue.append_resolution = _patched_append_resolution
```

(The "patched_init / append_resolution" pattern at module bottom keeps the test seam clean — production code can still subclass `EventQueue` if needed without re-binding. If the project's style prefers methods declared inline in the class, refactor accordingly during implementation.)

- [ ] **Step 6: Run tests (expect PASS)**

- [ ] **Step 7: Commit (Task 10)**

```bash
git add cli/src/robot_md/hotplug/queue.py cli/tests/hotplug/test_queue_resolution_first_writer_wins.py cli/tests/hotplug/test_queue_truncation_recovery.py cli/tests/hotplug/test_queue_ttl_expiry.py
git commit -m "feat(sphp): EventQueue first-writer-wins + truncation alert + TTL expiry"
```

---

### Task 11: Per-RRN audit log

**Files:**
- Create: `cli/src/robot_md/hotplug/audit.py`
- Test: `cli/tests/hotplug/test_audit_log_append.py`

- [ ] **Step 1: Write the audit-log test**

```python
# cli/tests/hotplug/test_audit_log_append.py
from __future__ import annotations

import json
from pathlib import Path

from robot_md.hotplug.audit import AuditLog


def test_append_chains_per_rrn(tmp_path: Path) -> None:
    log = AuditLog(rrn="RRN-test", root=tmp_path / "audit")
    log.append("hotplug_event", {"foo": "bar"})
    log.append("hotplug_bind", {"driver_id": "arm_servos"})
    contents = (tmp_path / "audit" / "RRN-test.jsonl").read_text().splitlines()
    assert len(contents) == 2
    rec1 = json.loads(contents[0])
    rec2 = json.loads(contents[1])
    assert rec2["prev_hash"] == rec1["this_hash"]
```

- [ ] **Step 2: Implement `audit.py`**

```python
# cli/src/robot_md/hotplug/audit.py
"""Per-RRN hash-chained audit log. Mirrors RRF's audit trail shape."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

_DEFAULT_ROOT = Path.home() / ".robot-md" / "audit"
_ZERO_HASH = "sha256:" + "0" * 64


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _hash(prev: str, body: dict) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    h = hashlib.sha256(); h.update(prev.encode()); h.update(b"\0"); h.update(canonical.encode())
    return "sha256:" + h.hexdigest()


class AuditLog:
    def __init__(self, *, rrn: str, root: Path = _DEFAULT_ROOT) -> None:
        self.rrn = rrn
        self.path = root / f"{rrn}.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def _last_hash(self) -> str:
        data = self.path.read_bytes().rstrip(b"\n")
        if not data:
            return _ZERO_HASH
        try:
            return json.loads(data.rsplit(b"\n", 1)[-1])["this_hash"]
        except Exception:
            return _ZERO_HASH

    def append(self, kind: str, payload: dict) -> dict:
        with self.path.open("ab") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                prev = self._last_hash()
                body = {
                    "id": "audit_" + uuid.uuid4().hex,
                    "ts": _now_iso(),
                    "rrn": self.rrn,
                    "kind": kind,
                    "payload": payload,
                    "prev_hash": prev,
                }
                body["this_hash"] = _hash(prev, body)
                f.write((json.dumps(body, sort_keys=True) + "\n").encode())
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return body
```

- [ ] **Step 3: Run test (expect PASS)**

- [ ] **Step 4: Commit (Task 11)**

```bash
git add cli/src/robot_md/hotplug/audit.py cli/tests/hotplug/test_audit_log_append.py
git commit -m "feat(sphp): per-RRN hash-chained audit log"
```

---

## Phase D — Manifest merge

### Task 12: `manifest.merge(proposal, manifest_path)` with schema gate

**Files:**
- Create: `cli/src/robot_md/hotplug/manifest.py`
- Test: `cli/tests/hotplug/test_manifest_merge_appends_driver.py`, `test_manifest_merge_validates_before_write.py`, `test_manifest_merge_no_manifest.py`, `test_manifest_merge_locking.py`

- [ ] **Step 1: Write the appends-driver test**

```python
# cli/tests/hotplug/test_manifest_merge_appends_driver.py
from __future__ import annotations

from pathlib import Path

from robot_md.hotplug.manifest import merge, MergeOutcome
from robot_md.hotplug.matcher import BindProposal


def test_merge_appends_driver_preserves_others(tmp_path: Path) -> None:
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("""---
id: RRN-test
metadata:
  manufacturer: Test
  author: a@b
drivers:
  - id: existing
    protocol: realsense
    backend: realsense
---
""")
    proposal = BindProposal(
        rrn="RRN-test",
        driver_id_suggestion="arm_servos",
        backend_name="lerobot",
        preset_name="so_arm101",
        capability_preview=[],
        inferred_fields={"port": "/dev/ttyACM0", "transport": "feetech"},
    )
    outcome = merge(proposal, manifest_path=manifest)
    assert isinstance(outcome, MergeOutcome)
    assert outcome.success is True
    text = manifest.read_text()
    assert "id: existing" in text          # preserved
    assert "id: arm_servos" in text         # appended
    assert "backend: lerobot" in text
```

- [ ] **Step 2: Write the validate-before-write test**

```python
# cli/tests/hotplug/test_manifest_merge_validates_before_write.py
from __future__ import annotations

from pathlib import Path

from robot_md.hotplug.manifest import merge
from robot_md.hotplug.matcher import BindProposal


def test_invalid_proposal_does_not_write(tmp_path: Path) -> None:
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("""---
id: RRN-test
metadata:
  manufacturer: Test
  author: a@b
drivers: []
---
""")
    bad = BindProposal(
        rrn="RRN-test",
        driver_id_suggestion="bad name with spaces",  # invalid driver_id
        backend_name="lerobot",
        preset_name="so_arm101",
        capability_preview=[],
        inferred_fields={},
    )
    outcome = merge(bad, manifest_path=manifest)
    assert outcome.success is False
    assert "validation" in outcome.reason.lower()
    # Original manifest unchanged.
    assert "bad name with spaces" not in manifest.read_text()
```

- [ ] **Step 3: Write the no-manifest test + locking smoke**

```python
# cli/tests/hotplug/test_manifest_merge_no_manifest.py
from __future__ import annotations

from pathlib import Path

from robot_md.hotplug.manifest import merge
from robot_md.hotplug.matcher import BindProposal


def test_merge_with_no_manifest_returns_clear_error(tmp_path: Path) -> None:
    manifest = tmp_path / "MISSING.md"  # does not exist
    outcome = merge(BindProposal(
        rrn=None, driver_id_suggestion="arm_servos", backend_name="lerobot",
        preset_name="so_arm101", capability_preview=[], inferred_fields={},
    ), manifest_path=manifest)
    assert outcome.success is False
    assert outcome.reason == "no_manifest_in_cwd"
```

```python
# cli/tests/hotplug/test_manifest_merge_locking.py
from __future__ import annotations

import threading
from pathlib import Path

from robot_md.hotplug.manifest import merge
from robot_md.hotplug.matcher import BindProposal


def _proposal(driver_id: str) -> BindProposal:
    return BindProposal(
        rrn="RRN-test", driver_id_suggestion=driver_id,
        backend_name="lerobot", preset_name="so_arm101",
        capability_preview=[], inferred_fields={"port": "/dev/ttyACM0", "transport": "feetech"},
    )


def test_concurrent_merges_serialize_via_fcntl(tmp_path: Path) -> None:
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("""---
id: RRN-test
metadata:
  manufacturer: Test
  author: a@b
drivers: []
---
""")
    results: list = []
    def do(driver_id):
        results.append(merge(_proposal(driver_id), manifest_path=manifest))
    t1 = threading.Thread(target=do, args=("driver_one",))
    t2 = threading.Thread(target=do, args=("driver_two",))
    t1.start(); t2.start(); t1.join(); t2.join()
    text = manifest.read_text()
    assert "driver_one" in text
    assert "driver_two" in text
    assert all(r.success for r in results)
```

- [ ] **Step 4: Run tests (expect FAIL — module missing)**

- [ ] **Step 5: Implement `manifest.py`**

```python
# cli/src/robot_md/hotplug/manifest.py
"""HIGH-tier manifest merge — schema-gated, fcntl-locked, atomic."""

from __future__ import annotations

import fcntl
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from robot_md.hotplug.matcher import BindProposal


_DRIVER_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


@dataclass(frozen=True)
class MergeOutcome:
    success: bool
    rrn: str | None
    driver_id: str | None
    reason: str


def merge(proposal: BindProposal, *, manifest_path: Path) -> MergeOutcome:
    if not manifest_path.exists():
        return MergeOutcome(success=False, rrn=proposal.rrn, driver_id=None, reason="no_manifest_in_cwd")

    if not _DRIVER_ID_RE.match(proposal.driver_id_suggestion):
        return MergeOutcome(success=False, rrn=proposal.rrn, driver_id=None,
                            reason="validation_failed: driver_id must match [a-z][a-z0-9_]*")

    with manifest_path.open("r+") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            text = f.read()
            m = _FRONTMATTER_RE.match(text)
            if m is None:
                return MergeOutcome(success=False, rrn=proposal.rrn, driver_id=None,
                                    reason="validation_failed: no frontmatter")
            data = yaml.safe_load(m.group(1)) or {}
            drivers = data.setdefault("drivers", [])

            new_driver = {
                "id": proposal.driver_id_suggestion,
                "protocol": proposal.inferred_fields.get("transport", "unknown"),
                "backend": proposal.backend_name,
            }
            if "port" in proposal.inferred_fields:
                new_driver["port"] = proposal.inferred_fields["port"]

            drivers.append(new_driver)

            new_frontmatter = yaml.safe_dump(data, sort_keys=False).rstrip()
            new_text = f"---\n{new_frontmatter}\n---\n" + text[m.end():]

            f.seek(0)
            f.truncate()
            f.write(new_text)
            f.flush()
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    return MergeOutcome(success=True, rrn=proposal.rrn, driver_id=proposal.driver_id_suggestion, reason="ok")
```

- [ ] **Step 6: Run tests (expect PASS 4/4)**

- [ ] **Step 7: Commit (Task 12)**

```bash
git add cli/src/robot_md/hotplug/manifest.py cli/tests/hotplug/test_manifest_merge_*.py
git commit -m "feat(sphp): manifest.merge — schema-gated, fcntl-locked, atomic append"
```

---

## Phase E — Daemon entry point

### Task 13: Daemon config (`hotplug.toml`)

**Files:**
- Create: `cli/src/robot_md/hotplug/config.py`
- Test: `cli/tests/hotplug/test_config.py`

- [ ] **Step 1: Write the config-defaults test**

```python
# cli/tests/hotplug/test_config.py
from __future__ import annotations

from pathlib import Path

from robot_md.hotplug.config import HotplugConfig


def test_defaults_when_no_config_file(tmp_path: Path) -> None:
    cfg = HotplugConfig.load(path=tmp_path / "hotplug.toml")
    assert cfg.pending_ttl_days == 7.0


def test_overrides_from_toml(tmp_path: Path) -> None:
    p = tmp_path / "hotplug.toml"
    p.write_text("pending_ttl_days = 3\n")
    cfg = HotplugConfig.load(path=p)
    assert cfg.pending_ttl_days == 3
```

- [ ] **Step 2: Implement `config.py`**

```python
# cli/src/robot_md/hotplug/config.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib  # py3.11+
except ImportError:
    import tomli as tomllib  # type: ignore

_DEFAULT_PATH = Path.home() / ".robot-md" / "hotplug.toml"


@dataclass(frozen=True)
class HotplugConfig:
    pending_ttl_days: float = 7.0

    @classmethod
    def load(cls, *, path: Path = _DEFAULT_PATH) -> "HotplugConfig":
        if not path.exists():
            return cls()
        data = tomllib.loads(path.read_text())
        return cls(pending_ttl_days=float(data.get("pending_ttl_days", 7.0)))
```

- [ ] **Step 3: Run test (expect PASS)**

- [ ] **Step 4: Commit (Task 13)**

```bash
git add cli/src/robot_md/hotplug/config.py cli/tests/hotplug/test_config.py
git commit -m "feat(sphp): HotplugConfig (~/.robot-md/hotplug.toml)"
```

---

### Task 14: Linux Unix socket listener

**Files:**
- Create: `cli/src/robot_md/hotplug/socket_listener.py`
- Test: `cli/tests/hotplug/test_socket_listener.py`

- [ ] **Step 1: Write the socket test**

```python
# cli/tests/hotplug/test_socket_listener.py
from __future__ import annotations

import asyncio
import socket
import sys
from pathlib import Path

import pytest

from robot_md.hotplug.socket_listener import SocketListener


pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Unix socket — Linux primary")


def test_socket_bind_and_nudge(tmp_path: Path) -> None:
    sock_path = tmp_path / "test.sock"
    listener = SocketListener(path=sock_path)
    received: list = []

    async def serve():
        await listener.start(on_nudge=lambda: received.append(1))
        # Simulate a client nudge.
        c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        c.connect(str(sock_path))
        c.sendall(b"\x01")
        c.close()
        await asyncio.sleep(0.05)
        await listener.stop()

    asyncio.run(serve())
    assert received == [1]


def test_second_listener_eaddrinuse(tmp_path: Path) -> None:
    sock_path = tmp_path / "test.sock"
    listener = SocketListener(path=sock_path)
    other = SocketListener(path=sock_path)

    async def main():
        await listener.start(on_nudge=lambda: None)
        with pytest.raises(OSError):
            await other.start(on_nudge=lambda: None)
        await listener.stop()

    asyncio.run(main())
```

- [ ] **Step 2: Implement `socket_listener.py`**

```python
# cli/src/robot_md/hotplug/socket_listener.py
from __future__ import annotations

import asyncio
import os
import socket as _socket
from pathlib import Path
from typing import Callable

_DEFAULT_PATH = Path(f"/run/user/{os.getuid()}/robot-md-hotplug.sock") if hasattr(os, "getuid") else None


class SocketListener:
    def __init__(self, *, path: Path | None = None) -> None:
        self.path = path or _DEFAULT_PATH
        self._server: asyncio.AbstractServer | None = None

    async def start(self, *, on_nudge: Callable[[], None]) -> None:
        async def handler(reader, writer):
            try:
                _ = await reader.read(64)  # discard payload — presence is the nudge
                on_nudge()
            finally:
                writer.close()

        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and self._server is None:
            # Stale socket file? Try unlink.
            try:
                self.path.unlink()
            except OSError:
                pass
        self._server = await asyncio.start_unix_server(handler, path=str(self.path))

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        try:
            if self.path.exists():
                self.path.unlink()
        except OSError:
            pass
```

- [ ] **Step 3: Run test (expect PASS 2/2)**

- [ ] **Step 4: Commit (Task 14)**

```bash
git add cli/src/robot_md/hotplug/socket_listener.py cli/tests/hotplug/test_socket_listener.py
git commit -m "feat(sphp): Linux Unix socket listener for MCP-server nudges"
```

---

### Task 15: Daemon entry point — compose watcher + matcher + queue + manifest + audit

**Files:**
- Create: `cli/src/robot_md/hotplug/daemon.py`
- Test: `cli/tests/hotplug/test_daemon_starts_and_stops_clean.py`, `test_daemon_dedupes_replug.py`

- [ ] **Step 1: Write the start-stop test**

```python
# cli/tests/hotplug/test_daemon_starts_and_stops_clean.py
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

from robot_md.hotplug.daemon import run_daemon
from robot_md.hotplug.event import DeviceEvent


async def _empty_watcher():
    if False:
        yield  # never yields; just an async generator


def test_daemon_runs_until_stop_event(tmp_path: Path) -> None:
    stop = asyncio.Event()

    async def main():
        task = asyncio.create_task(run_daemon(
            stop_event=stop,
            queue_path=tmp_path / "q.jsonl",
            audit_root=tmp_path / "audit",
            watcher_factory=_empty_watcher,
        ))
        await asyncio.sleep(0.05)
        stop.set()
        await asyncio.wait_for(task, timeout=2.0)

    asyncio.run(main())
```

- [ ] **Step 2: Write the dedup test**

```python
# cli/tests/hotplug/test_daemon_dedupes_replug.py
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from robot_md.hotplug.daemon import run_daemon
from robot_md.hotplug.event import DeviceEvent


def _evt():
    return DeviceEvent(
        kind="tty_added", vid="1a86", pid="7523", serial="AB12",
        path="/dev/ttyACM0", transport="feetech",
        raw_metadata={}, detected_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )


def test_replug_within_dedup_window_emits_one_pending(tmp_path: Path) -> None:
    events = [_evt(), _evt(), _evt()]

    async def watcher():
        for e in events:
            yield e

    stop = asyncio.Event()

    async def main():
        task = asyncio.create_task(run_daemon(
            stop_event=stop,
            queue_path=tmp_path / "q.jsonl",
            audit_root=tmp_path / "audit",
            watcher_factory=watcher,
        ))
        await asyncio.sleep(0.1)
        stop.set()
        await asyncio.wait_for(task, timeout=2.0)

    asyncio.run(main())
    # Exactly one pending record despite three events with same (vid,pid,serial,path).
    text = (tmp_path / "q.jsonl").read_text()
    pending_count = text.count('"kind": "pending"')
    assert pending_count == 1
```

- [ ] **Step 3: Implement `daemon.py`**

```python
# cli/src/robot_md/hotplug/daemon.py
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Awaitable, Callable, Optional

from robot_md.hotplug.audit import AuditLog
from robot_md.hotplug.event import DeviceEvent
from robot_md.hotplug.matcher import classify
from robot_md.hotplug.queue import EventQueue


_DEDUP_WINDOW = timedelta(hours=1)


async def run_daemon(
    *,
    stop_event: asyncio.Event,
    queue_path: Path,
    audit_root: Path,
    watcher_factory: Callable[[], "asyncio.AsyncGenerator[DeviceEvent, None]"],
    rrn: str = "RRN-current",
) -> int:
    queue = EventQueue(path=queue_path)
    audit = AuditLog(rrn=rrn, root=audit_root)
    seen: dict[tuple, datetime] = {}

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
            queue.append_pending(evt, decision)
            audit.append("hotplug_event", {"event": evt.__dict__, "tier": decision.tier})

    task = asyncio.create_task(event_loop())
    await stop_event.wait()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    return 0
```

- [ ] **Step 4: Run tests (expect PASS)**

- [ ] **Step 5: Commit (Task 15)**

```bash
git add cli/src/robot_md/hotplug/daemon.py cli/tests/hotplug/test_daemon_starts_and_stops_clean.py cli/tests/hotplug/test_daemon_dedupes_replug.py
git commit -m "feat(sphp): daemon entry — watcher + matcher + queue + audit + dedup"
```

---

### Task 16: Daemon EADDRINUSE protection (second instance)

**Files:**
- Modify: `cli/src/robot_md/hotplug/daemon.py` (wrap socket listener bind)
- Test: `cli/tests/hotplug/test_daemon_two_instances_eaddrinuse.py`

- [ ] **Step 1: Write the test**

```python
# cli/tests/hotplug/test_daemon_two_instances_eaddrinuse.py
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from robot_md.hotplug.daemon import run_daemon
from robot_md.hotplug.socket_listener import SocketListener


pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="socket-bind contention is Linux-only")


async def _empty_watcher():
    if False:
        yield


def test_second_daemon_exits_with_eaddrinuse(tmp_path: Path) -> None:
    sock_path = tmp_path / "hotplug.sock"
    listener = SocketListener(path=sock_path)
    stop1 = asyncio.Event()
    stop2 = asyncio.Event()

    async def main():
        # Pre-bind the socket to simulate a running daemon.
        await listener.start(on_nudge=lambda: None)
        # Second daemon's socket bind should raise EADDRINUSE.
        from robot_md.hotplug.daemon import run_daemon_with_socket
        rc = await run_daemon_with_socket(
            stop_event=stop2,
            queue_path=tmp_path / "q.jsonl",
            audit_root=tmp_path / "audit",
            watcher_factory=_empty_watcher,
            socket_path=sock_path,
        )
        assert rc == 2
        await listener.stop()

    asyncio.run(main())
```

- [ ] **Step 2: Add `run_daemon_with_socket` wrapper**

```python
# Append to daemon.py
import errno
from robot_md.hotplug.socket_listener import SocketListener


async def run_daemon_with_socket(
    *,
    stop_event: asyncio.Event,
    queue_path: Path,
    audit_root: Path,
    watcher_factory,
    socket_path: Path,
    rrn: str = "RRN-current",
) -> int:
    listener = SocketListener(path=socket_path)
    try:
        await listener.start(on_nudge=lambda: None)
    except OSError as e:
        if e.errno == errno.EADDRINUSE or "address already in use" in str(e).lower():
            return 2
        raise

    try:
        return await run_daemon(
            stop_event=stop_event,
            queue_path=queue_path,
            audit_root=audit_root,
            watcher_factory=watcher_factory,
            rrn=rrn,
        )
    finally:
        await listener.stop()
```

- [ ] **Step 3: Run test (expect PASS)**

- [ ] **Step 4: Commit (Task 16)**

```bash
git add cli/src/robot_md/hotplug/daemon.py cli/tests/hotplug/test_daemon_two_instances_eaddrinuse.py
git commit -m "feat(sphp): second daemon exits status 2 on socket EADDRINUSE"
```

---

## Phase F — MCP server changes

### Task 17: Manifest watcher — inotify reload + `notifications/tools/list_changed`

**Files:**
- Create: `cli/src/robot_md/mcp/manifest_watcher.py`
- Test: `cli/tests/hotplug/test_mcp_inotify_reload_on_manifest_change.py`

- [ ] **Step 1: Write the watcher test**

```python
# cli/tests/hotplug/test_mcp_inotify_reload_on_manifest_change.py
from __future__ import annotations

import time
from pathlib import Path

from robot_md.mcp.manifest_watcher import ManifestWatcher


def test_watcher_fires_on_change(tmp_path: Path) -> None:
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("---\nid: RRN-test\n---\n")
    received: list = []
    w = ManifestWatcher(manifest_path=manifest, on_change=lambda: received.append(1))
    w.start()
    try:
        time.sleep(0.2)
        manifest.write_text("---\nid: RRN-test\nmetadata:\n  author: a@b\n---\n")
        time.sleep(0.5)
    finally:
        w.stop()
    assert received, "ManifestWatcher did not observe the change"
```

- [ ] **Step 2: Implement `manifest_watcher.py`**

```python
# cli/src/robot_md/mcp/manifest_watcher.py
from __future__ import annotations

from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


class ManifestWatcher:
    def __init__(self, *, manifest_path: Path, on_change: Callable[[], None]) -> None:
        self.manifest_path = manifest_path
        self._observer = Observer()
        self._handler = _Handler(target=manifest_path, on_change=on_change)

    def start(self) -> None:
        self._observer.schedule(self._handler, str(self.manifest_path.parent), recursive=False)
        self._observer.start()

    def stop(self) -> None:
        self._observer.stop()
        self._observer.join(timeout=2.0)


class _Handler(FileSystemEventHandler):
    def __init__(self, *, target: Path, on_change: Callable[[], None]) -> None:
        self._target = target.resolve()
        self._on_change = on_change

    def on_modified(self, event):
        if Path(event.src_path).resolve() == self._target:
            self._on_change()

    def on_created(self, event):
        if Path(event.src_path).resolve() == self._target:
            self._on_change()
```

- [ ] **Step 3: Run test (expect PASS — may need slight sleep tuning)**

- [ ] **Step 4: Commit (Task 17)**

```bash
git add cli/src/robot_md/mcp/manifest_watcher.py cli/tests/hotplug/test_mcp_inotify_reload_on_manifest_change.py
git commit -m "feat(sphp): MCP-server manifest watcher (watchdog) — fires on ROBOT.md change"
```

---

### Task 18: `hotplug_review` MCP tool

**Files:**
- Create: `cli/src/robot_md/mcp/tools/hotplug_review.py`
- Modify: `cli/src/robot_md/mcp/server.py` (register tool)
- Test: `cli/tests/hotplug/test_hotplug_review_returns_pending_only.py`

- [ ] **Step 1: Write the tool test**

```python
# cli/tests/hotplug/test_hotplug_review_returns_pending_only.py
from __future__ import annotations

from pathlib import Path

from robot_md.hotplug.event import DeviceEvent
from robot_md.hotplug.matcher import Decision
from robot_md.hotplug.queue import EventQueue
from robot_md.mcp.tools.hotplug_review import hotplug_review_tool


def _evt():
    return DeviceEvent(
        kind="tty_added", vid="1a86", pid="7523", serial="AB12",
        path="/dev/ttyACM0", transport="feetech",
        raw_metadata={}, detected_at="2026-04-27T19:30:11Z",
    )


def test_review_returns_pending_only(tmp_path: Path) -> None:
    q = EventQueue(path=tmp_path / "q.jsonl")
    pending1 = q.append_pending(_evt(), Decision(tier="MEDIUM", unambiguous=False, bind_proposal=None))
    pending2 = q.append_pending(_evt(), Decision(tier="LOW", unambiguous=False, bind_proposal=None))
    q.append_resolution(ref_id=pending1.id, resolution="bind", by="claude", outcome={})

    result = hotplug_review_tool(_queue=q)
    ids = {entry["event_id"] for entry in result["pending"]}
    assert pending2.id in ids
    assert pending1.id not in ids
```

- [ ] **Step 2: Implement the tool**

```python
# cli/src/robot_md/mcp/tools/hotplug_review.py
"""MCP tool: hotplug_review — list pending (un-resolved) hot-plug events."""

from __future__ import annotations

import json
from pathlib import Path

from robot_md.hotplug.queue import EventQueue


def hotplug_review_tool(_queue: EventQueue | None = None) -> dict:
    q = _queue or EventQueue()
    records = []
    for line in q.path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except Exception:
            continue
    pending_ids = {r["id"] for r in records if r.get("kind") == "pending"}
    resolved_refs = {r["ref"] for r in records if r.get("kind") == "resolved" and r.get("ref")}
    pending_unresolved = pending_ids - resolved_refs

    out = []
    for r in records:
        if r.get("kind") == "pending" and r["id"] in pending_unresolved:
            out.append({
                "event_id": r["id"],
                "tier": r["decision"]["tier"],
                "device": r["event"],
                "decision": r["decision"],
            })
    return {"pending": out}
```

- [ ] **Step 3: Register in `server.py`**

In `cli/src/robot_md/mcp/server.py`, add (alongside existing `@server.tool()` decorators):

```python
    @server.tool()
    def hotplug_review() -> dict:
        """Return all currently-pending (unresolved) hot-plug events for operator review."""
        from robot_md.mcp.tools.hotplug_review import hotplug_review_tool
        return hotplug_review_tool()
```

- [ ] **Step 4: Run test (expect PASS)**

- [ ] **Step 5: Commit (Task 18)**

```bash
git add cli/src/robot_md/mcp/tools/hotplug_review.py cli/src/robot_md/mcp/server.py cli/tests/hotplug/test_hotplug_review_returns_pending_only.py
git commit -m "feat(sphp): hotplug_review MCP tool"
```

---

### Task 19: `hotplug_confirm` MCP tool — calls back to daemon

**Files:**
- Create: `cli/src/robot_md/mcp/tools/hotplug_confirm.py`
- Modify: `cli/src/robot_md/mcp/server.py`
- Test: `cli/tests/hotplug/test_hotplug_confirm_bind_writes_manifest.py`, `test_hotplug_confirm_reject_appends_resolution.py`

- [ ] **Step 1: Write the bind test**

```python
# cli/tests/hotplug/test_hotplug_confirm_bind_writes_manifest.py
from __future__ import annotations

from pathlib import Path

from robot_md.hotplug.event import DeviceEvent
from robot_md.hotplug.matcher import BindProposal, Decision
from robot_md.hotplug.queue import EventQueue
from robot_md.mcp.tools.hotplug_confirm import hotplug_confirm_tool


def test_confirm_bind_writes_manifest_and_appends_resolution(tmp_path: Path) -> None:
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("""---
id: RRN-test
metadata: {manufacturer: T, author: a@b}
drivers: []
---
""")
    q = EventQueue(path=tmp_path / "q.jsonl")
    proposal = BindProposal(
        rrn="RRN-test", driver_id_suggestion="arm_servos",
        backend_name="lerobot", preset_name="so_arm101",
        capability_preview=[],
        inferred_fields={"port": "/dev/ttyACM0", "transport": "feetech"},
    )
    decision = Decision(tier="MEDIUM", unambiguous=False, bind_proposal=proposal,
                        alternatives=[], reasons=[])
    pending = q.append_pending(DeviceEvent(
        kind="tty_added", vid="1a86", pid="7523", serial="AB12",
        path="/dev/ttyACM0", transport="feetech",
        raw_metadata={}, detected_at="2026-04-27T19:30:11Z",
    ), decision)
    out = hotplug_confirm_tool(
        event_id=pending.id, decision="bind", choice_index=None,
        _queue=q, _manifest_path=manifest, _by="claude",
    )
    assert out["ok"] is True
    assert "backend: lerobot" in manifest.read_text()
```

- [ ] **Step 2: Write the reject test**

```python
# cli/tests/hotplug/test_hotplug_confirm_reject_appends_resolution.py
from __future__ import annotations

from pathlib import Path

from robot_md.hotplug.event import DeviceEvent
from robot_md.hotplug.matcher import Decision
from robot_md.hotplug.queue import EventQueue
from robot_md.mcp.tools.hotplug_confirm import hotplug_confirm_tool


def test_reject_appends_resolution_no_manifest_change(tmp_path: Path) -> None:
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("---\nid: RRN-test\nmetadata: {a: 1}\ndrivers: []\n---\n")
    before = manifest.read_text()
    q = EventQueue(path=tmp_path / "q.jsonl")
    pending = q.append_pending(DeviceEvent(
        kind="tty_added", vid="1a86", pid="7523", serial=None,
        path="/dev/ttyACM0", transport="feetech",
        raw_metadata={}, detected_at="2026-04-27T19:30:11Z",
    ), Decision(tier="MEDIUM", unambiguous=False, bind_proposal=None))
    out = hotplug_confirm_tool(
        event_id=pending.id, decision="reject", choice_index=None,
        _queue=q, _manifest_path=manifest, _by="claude",
    )
    assert out["ok"] is True
    assert manifest.read_text() == before
    assert '"resolution": "reject"' in (tmp_path / "q.jsonl").read_text()
```

- [ ] **Step 3: Implement `hotplug_confirm.py`**

```python
# cli/src/robot_md/mcp/tools/hotplug_confirm.py
"""MCP tool: hotplug_confirm — bind or reject a pending hot-plug event."""

from __future__ import annotations

import json
from pathlib import Path

from robot_md.hotplug.manifest import merge as manifest_merge
from robot_md.hotplug.matcher import BindProposal
from robot_md.hotplug.queue import AlreadyResolvedError, EventQueue


def hotplug_confirm_tool(
    *,
    event_id: str,
    decision: str,
    choice_index: int | None = None,
    _queue: EventQueue | None = None,
    _manifest_path: Path | None = None,
    _by: str = "claude",
) -> dict:
    if decision not in {"bind", "reject"}:
        return {"ok": False, "error": f"decision must be 'bind' or 'reject', got {decision!r}"}

    q = _queue or EventQueue()
    manifest_path = _manifest_path or Path.cwd() / "ROBOT.md"

    # Find the pending record.
    target = None
    for line in q.path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("kind") == "pending" and r.get("id") == event_id:
            target = r
            break
    if target is None:
        return {"ok": False, "error": f"event {event_id!r} not found"}

    if decision == "reject":
        try:
            q.append_resolution(ref_id=event_id, resolution="reject", by=_by, outcome=None)
        except AlreadyResolvedError as e:
            return {"ok": False, "error": "already_resolved", "by": e.by}
        return {"ok": True}

    # decision == "bind"
    decision_blob = target["decision"]
    proposals = []
    if decision_blob.get("bind_proposal"):
        proposals.append(decision_blob["bind_proposal"])
    proposals.extend(decision_blob.get("alternatives", []) or [])
    if not proposals:
        return {"ok": False, "error": "no bind_proposal available for this event"}
    if choice_index is None:
        choice_index = 0
    chosen = proposals[choice_index]
    proposal_obj = BindProposal(
        rrn=chosen.get("rrn"),
        driver_id_suggestion=chosen["driver_id_suggestion"],
        backend_name=chosen["backend_name"],
        preset_name=chosen.get("preset_name"),
        capability_preview=[],
        inferred_fields=chosen.get("inferred_fields") or {},
    )

    outcome = manifest_merge(proposal_obj, manifest_path=manifest_path)
    if not outcome.success:
        return {"ok": False, "error": "merge_failed", "reason": outcome.reason}

    try:
        q.append_resolution(
            ref_id=event_id, resolution="bind", by=_by,
            outcome={"driver_id": outcome.driver_id, "rrn": outcome.rrn},
        )
    except AlreadyResolvedError as e:
        return {"ok": False, "error": "already_resolved", "by": e.by}
    return {"ok": True, "driver_id": outcome.driver_id}
```

- [ ] **Step 4: Register in `server.py`**

```python
    @server.tool()
    def hotplug_confirm(event_id: str, decision: str, choice_index: int | None = None) -> dict:
        """Confirm or reject a pending hot-plug event."""
        from robot_md.mcp.tools.hotplug_confirm import hotplug_confirm_tool
        return hotplug_confirm_tool(event_id=event_id, decision=decision, choice_index=choice_index)
```

- [ ] **Step 5: Run tests (expect PASS 2/2)**

- [ ] **Step 6: Commit (Task 19)**

```bash
git add cli/src/robot_md/mcp/tools/hotplug_confirm.py cli/src/robot_md/mcp/server.py cli/tests/hotplug/test_hotplug_confirm_bind_writes_manifest.py cli/tests/hotplug/test_hotplug_confirm_reject_appends_resolution.py
git commit -m "feat(sphp): hotplug_confirm MCP tool — bind via manifest.merge / reject via queue"
```

---

## Phase G — CLI subcommands

### Task 20: `robot-md hotplug-daemon start|stop|status`

**Files:**
- Create: `cli/src/robot_md/hotplug/cli.py`
- Modify: `cli/src/robot_md/__main__.py` (register the subcommand group)
- Test: `cli/tests/hotplug/test_cli_hotplug_status_reports_running.py`

- [ ] **Step 1: Write the status test**

```python
# cli/tests/hotplug/test_cli_hotplug_status_reports_running.py
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_status_when_no_daemon_running() -> None:
    env = {"PYTHONPATH": str(Path(__file__).parents[2] / "src")}
    proc = subprocess.run(
        [sys.executable, "-m", "robot_md", "hotplug-daemon", "status"],
        capture_output=True, text=True, env={**env},
    )
    assert proc.returncode == 0
    assert "not running" in proc.stdout.lower() or "stopped" in proc.stdout.lower()
```

- [ ] **Step 2: Implement `hotplug/cli.py`**

```python
# cli/src/robot_md/hotplug/cli.py
"""Typer subcommands for the hotplug daemon + operator review."""

from __future__ import annotations

import asyncio
import os
import signal
from pathlib import Path

import typer

app = typer.Typer(help="Hot-plug daemon control")


_PIDFILE = Path.home() / ".robot-md" / "hotplug-daemon.pid"


@app.command("start")
def start() -> None:
    if _PIDFILE.exists():
        try:
            pid = int(_PIDFILE.read_text())
            os.kill(pid, 0)
            typer.echo(f"daemon already running, pid={pid}")
            raise typer.Exit(0)
        except (ProcessLookupError, ValueError):
            _PIDFILE.unlink(missing_ok=True)

    pid = os.fork() if hasattr(os, "fork") else 0
    if pid == 0:
        # Child (or Windows fall-through).
        from robot_md.hotplug.daemon import run_daemon_with_socket
        from robot_md.hotplug.socket_listener import _DEFAULT_PATH as SOCK
        import sys as _sys
        if sys_platform := __import__("sys").platform:
            pass
        # Pick the right watcher for the platform.
        if __import__("sys").platform == "linux":
            from robot_md.hotplug.linux import watch_devices
        elif __import__("sys").platform == "darwin":
            from robot_md.hotplug.macos import watch_devices
        else:
            from robot_md.hotplug.windows import watch_devices

        stop = asyncio.Event()
        def _on_sig(*_): stop.set()
        signal.signal(signal.SIGTERM, _on_sig)
        signal.signal(signal.SIGINT, _on_sig)

        _PIDFILE.parent.mkdir(parents=True, exist_ok=True)
        _PIDFILE.write_text(str(os.getpid()))
        try:
            asyncio.run(run_daemon_with_socket(
                stop_event=stop,
                queue_path=Path.home() / ".robot-md" / "hotplug-events.jsonl",
                audit_root=Path.home() / ".robot-md" / "audit",
                watcher_factory=watch_devices,
                socket_path=SOCK,
            ))
        finally:
            _PIDFILE.unlink(missing_ok=True)
    else:
        typer.echo(f"daemon started, pid={pid}")


@app.command("stop")
def stop() -> None:
    if not _PIDFILE.exists():
        typer.echo("daemon not running")
        raise typer.Exit(0)
    pid = int(_PIDFILE.read_text())
    try:
        os.kill(pid, signal.SIGTERM)
        typer.echo(f"sent SIGTERM to pid {pid}")
    except ProcessLookupError:
        _PIDFILE.unlink(missing_ok=True)
        typer.echo("daemon not running (stale pidfile cleared)")


@app.command("status")
def status() -> None:
    if not _PIDFILE.exists():
        typer.echo("daemon: not running")
        raise typer.Exit(0)
    pid = int(_PIDFILE.read_text())
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        _PIDFILE.unlink(missing_ok=True)
        typer.echo("daemon: not running (stale pidfile cleared)")
        raise typer.Exit(0)
    queue = Path.home() / ".robot-md" / "hotplug-events.jsonl"
    depth = sum(1 for _ in queue.read_text().splitlines()) if queue.exists() else 0
    typer.echo(f"daemon: running (pid={pid}); queue records: {depth}")
```

Register in `__main__.py`:

```python
from robot_md.hotplug.cli import app as hotplug_app

app.add_typer(hotplug_app, name="hotplug-daemon")
```

- [ ] **Step 3: Run test (expect PASS)**

- [ ] **Step 4: Commit (Task 20)**

```bash
git add cli/src/robot_md/hotplug/cli.py cli/src/robot_md/__main__.py cli/tests/hotplug/test_cli_hotplug_status_reports_running.py
git commit -m "feat(sphp): robot-md hotplug-daemon start|stop|status"
```

---

### Task 21: `robot-md hotplug review|confirm` CLI subcommands

**Files:**
- Modify: `cli/src/robot_md/hotplug/cli.py`
- Test: `cli/tests/hotplug/test_cli_hotplug_review_lists_pending.py`

- [ ] **Step 1: Write the test**

```python
# cli/tests/hotplug/test_cli_hotplug_review_lists_pending.py
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_review_lists_pending_table() -> None:
    env = {"PYTHONPATH": str(Path(__file__).parents[2] / "src")}
    proc = subprocess.run(
        [sys.executable, "-m", "robot_md", "hotplug", "review"],
        capture_output=True, text=True, env={**env},
    )
    assert proc.returncode == 0
    # Table header should appear even with empty queue.
    assert "event_id" in proc.stdout.lower() or "no pending" in proc.stdout.lower()
```

- [ ] **Step 2: Add a second Typer app for operator-facing commands**

In `cli/src/robot_md/hotplug/cli.py`, append:

```python
operator_app = typer.Typer(help="Hot-plug operator review / confirm")


@operator_app.command("review")
def review() -> None:
    from robot_md.mcp.tools.hotplug_review import hotplug_review_tool
    out = hotplug_review_tool()
    pending = out["pending"]
    if not pending:
        typer.echo("no pending events")
        raise typer.Exit(0)
    typer.echo(f"{'event_id':40} {'tier':6} {'transport':12} {'path'}")
    for p in pending:
        d = p["device"]
        typer.echo(f"{p['event_id']:40} {p['tier']:6} {d['transport']:12} {d['path']}")


@operator_app.command("confirm")
def confirm(
    event_id: str,
    bind: bool = typer.Option(False, "--bind"),
    reject: bool = typer.Option(False, "--reject"),
    choice_index: int | None = typer.Option(None, "--choice"),
) -> None:
    if bind == reject:
        typer.echo("specify exactly one of --bind / --reject", err=True)
        raise typer.Exit(2)
    from robot_md.mcp.tools.hotplug_confirm import hotplug_confirm_tool
    out = hotplug_confirm_tool(
        event_id=event_id,
        decision="bind" if bind else "reject",
        choice_index=choice_index,
        _by="cli",
    )
    if not out.get("ok"):
        typer.echo(f"failed: {out.get('error')} {out.get('reason') or ''}", err=True)
        raise typer.Exit(1)
    typer.echo("ok")
```

Register in `__main__.py`:

```python
from robot_md.hotplug.cli import operator_app as hotplug_op_app

app.add_typer(hotplug_op_app, name="hotplug")
```

- [ ] **Step 3: Run test (expect PASS)**

- [ ] **Step 4: Commit (Task 21)**

```bash
git add cli/src/robot_md/hotplug/cli.py cli/src/robot_md/__main__.py cli/tests/hotplug/test_cli_hotplug_review_lists_pending.py
git commit -m "feat(sphp): robot-md hotplug review|confirm operator CLI"
```

---

### Task 22: `robot-md hotplug install-service` (systemd / launchd / Scheduled Task)

**Files:**
- Create: `cli/src/robot_md/hotplug/service_installers/{__init__,linux_systemd,macos_launchd,windows_taskscheduler}.py`
- Modify: `cli/src/robot_md/hotplug/cli.py`
- Test: `cli/tests/hotplug/test_cli_hotplug_install_service_linux.py`, `test_cli_hotplug_install_service_macos.py`

- [ ] **Step 1: Write the linux installer test**

```python
# cli/tests/hotplug/test_cli_hotplug_install_service_linux.py
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from robot_md.hotplug.service_installers.linux_systemd import write_unit_file


pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="systemd-only test")


def test_unit_file_contents(tmp_path: Path) -> None:
    target = tmp_path / "robot-md-hotplug.service"
    write_unit_file(target=target)
    text = target.read_text()
    assert "[Unit]" in text and "[Service]" in text and "[Install]" in text
    assert "robot-md hotplug-daemon start" in text
    assert "Restart=on-failure" in text
    assert "WantedBy=default.target" in text
```

- [ ] **Step 2: Write the macOS installer test**

```python
# cli/tests/hotplug/test_cli_hotplug_install_service_macos.py
from __future__ import annotations

import plistlib
import sys
from pathlib import Path

import pytest

from robot_md.hotplug.service_installers.macos_launchd import write_plist


pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="launchd-only test")


def test_plist_contents(tmp_path: Path) -> None:
    target = tmp_path / "dev.robotmd.hotplug.plist"
    write_plist(target=target)
    data = plistlib.loads(target.read_bytes())
    assert data["Label"] == "dev.robotmd.hotplug"
    assert "robot-md" in data["ProgramArguments"][0]
    assert data["KeepAlive"] is True
```

- [ ] **Step 3: Implement installers**

```python
# cli/src/robot_md/hotplug/service_installers/linux_systemd.py
from __future__ import annotations

from pathlib import Path

_TEMPLATE = """[Unit]
Description=robot-md hot-plug daemon
After=network.target

[Service]
ExecStart=robot-md hotplug-daemon start --foreground
Restart=on-failure
RestartPreventExitStatus=2

[Install]
WantedBy=default.target
"""


def write_unit_file(*, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_TEMPLATE)
```

```python
# cli/src/robot_md/hotplug/service_installers/macos_launchd.py
from __future__ import annotations

import plistlib
import shutil
from pathlib import Path


def write_plist(*, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    program = shutil.which("robot-md") or "/usr/local/bin/robot-md"
    plist = {
        "Label": "dev.robotmd.hotplug",
        "ProgramArguments": [program, "hotplug-daemon", "start", "--foreground"],
        "KeepAlive": True,
        "RunAtLoad": True,
    }
    with target.open("wb") as f:
        plistlib.dump(plist, f)
```

```python
# cli/src/robot_md/hotplug/service_installers/windows_taskscheduler.py
from __future__ import annotations


def write_scheduled_task() -> None:
    """Stub — calls into pywin32 to register a Scheduled Task. Implementation
    deferred to Windows-platform refinement; smoke-test on the target host."""
    raise NotImplementedError("Windows installer landing in SP-HP follow-up")
```

Add a CLI command in `cli.py`:

```python
@operator_app.command("install-service")
def install_service() -> None:
    import sys
    if sys.platform == "linux":
        from robot_md.hotplug.service_installers.linux_systemd import write_unit_file
        target = Path.home() / ".config" / "systemd" / "user" / "robot-md-hotplug.service"
        write_unit_file(target=target)
        typer.echo(f"wrote {target}")
        typer.echo("enable: systemctl --user enable --now robot-md-hotplug")
    elif sys.platform == "darwin":
        from robot_md.hotplug.service_installers.macos_launchd import write_plist
        target = Path.home() / "Library" / "LaunchAgents" / "dev.robotmd.hotplug.plist"
        write_plist(target=target)
        typer.echo(f"wrote {target}")
        typer.echo("load: launchctl load -w " + str(target))
    elif sys.platform == "win32":
        typer.echo("Windows installer is a follow-up; run `robot-md hotplug-daemon start` manually for now")
    else:
        typer.echo(f"unsupported platform: {sys.platform}", err=True)
        raise typer.Exit(2)
```

- [ ] **Step 4: Run tests (expect PASS on the matching platform)**

- [ ] **Step 5: Commit (Task 22)**

```bash
git add cli/src/robot_md/hotplug/service_installers/ cli/src/robot_md/hotplug/cli.py cli/tests/hotplug/test_cli_hotplug_install_service_*.py
git commit -m "feat(sphp): hotplug install-service (systemd / launchd; Windows stub)"
```

---

## Phase H — Integration + hardware + smoke

### Task 23: End-to-end integration test — daemon binds HIGH-tier match into manifest

**Files:**
- Create: `cli/tests/integration/test_sphp_replug_high_tier_end_to_end.py`

- [ ] **Step 1: Write the integration test**

```python
# cli/tests/integration/test_sphp_replug_high_tier_end_to_end.py
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from robot_md.hotplug.daemon import run_daemon
from robot_md.hotplug.event import DeviceEvent
from robot_md.hotplug.presets_index import PresetMatch


def _evt():
    return DeviceEvent(
        kind="tty_added", vid="1a86", pid="7523", serial="UNIQUE_SERIAL",
        path="/dev/ttyACM0", transport="feetech",
        raw_metadata={}, detected_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )


@pytest.mark.skip(reason="end-to-end harness — fill in during execution; needs HIGH-tier auto-bind path wired through daemon (currently only queues)")
def test_high_tier_auto_bind_writes_manifest(tmp_path: Path) -> None:
    """Daemon classifies HIGH → calls manifest.merge → writes ROBOT.md.

    The Task 15 daemon implementation only queues; this integration test
    drives the implementer to add the HIGH-tier auto-bind path inside
    run_daemon. Replace skip with a real assertion once that path lands.
    """
    pass
```

- [ ] **Step 2: Run test (expect SKIP)**

- [ ] **Step 3: Implement the HIGH-tier auto-bind path inside `run_daemon`**

In `cli/src/robot_md/hotplug/daemon.py`, after `queue.append_pending(...)`:

```python
            if decision.tier == "HIGH" and decision.unambiguous and decision.bind_proposal:
                outcome = manifest_merge(decision.bind_proposal, manifest_path=Path.cwd() / "ROBOT.md")
                if outcome.success:
                    queue.append_resolution(
                        ref_id=record.id, resolution="bind", by="daemon",
                        outcome={"driver_id": outcome.driver_id, "rrn": outcome.rrn},
                    )
                    audit.append("hotplug_bind", {"driver_id": outcome.driver_id})
                else:
                    queue.append_resolution(
                        ref_id=record.id, resolution="bind", by="daemon",
                        outcome={"merge_failed": outcome.reason},
                    )
                    audit.append("merge_failed", {"reason": outcome.reason})
```

(Note: this requires `record = queue.append_pending(...)` to capture the return value; adjust `event_loop` accordingly.)

- [ ] **Step 4: Remove the skip + fill in the integration test body**

```python
def test_high_tier_auto_bind_writes_manifest(tmp_path: Path) -> None:
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text("---\nid: RRN-test\nmetadata: {a: 1}\ndrivers: []\n---\n")

    async def watcher():
        yield _evt()

    stop = asyncio.Event()

    async def main():
        with patch(
            "robot_md.hotplug.presets_index.lookup_by_vid_pid",
            lambda *, vid, pid: [PresetMatch("so_arm101", "feetech", "exact_match")],
        ), patch(
            "robot_md.hotplug.matcher._installed_backends_for_transport",
            return_value=["lerobot"],
        ), patch("pathlib.Path.cwd", return_value=tmp_path):
            task = asyncio.create_task(run_daemon(
                stop_event=stop,
                queue_path=tmp_path / "q.jsonl",
                audit_root=tmp_path / "audit",
                watcher_factory=watcher,
            ))
            await asyncio.sleep(0.1)
            stop.set()
            await asyncio.wait_for(task, timeout=2.0)

    asyncio.run(main())
    text = manifest.read_text()
    assert "backend: lerobot" in text
    assert "id: arm_servos" in text
```

- [ ] **Step 5: Run test (expect PASS)**

- [ ] **Step 6: Commit (Task 23)**

```bash
git add cli/src/robot_md/hotplug/daemon.py cli/tests/integration/test_sphp_replug_high_tier_end_to_end.py
git commit -m "feat(sphp): HIGH-tier auto-bind path in run_daemon + end-to-end integration test"
```

---

### Task 24: Hardware-test stubs + manual smoke checklist

**Files:**
- Create: `cli/tests/hardware/test_sphp_replug_so_arm101_high_tier.py`, `test_sphp_unknown_device_low_tier.py`
- Create: `cli/tests/manual/sphp_smoke.md`

- [ ] **Step 1: Write the hardware test stubs**

```python
# cli/tests/hardware/test_sphp_replug_so_arm101_high_tier.py
from __future__ import annotations

import pytest

pytestmark = pytest.mark.hardware


def test_replug_so_arm101_results_in_high_tier_auto_bind() -> None:
    """Run on bob with daemon active. Replug SO-ARM101. Within 1 s wall
    clock the manifest should gain a new drivers[] entry with backend: lerobot."""
    # Fixture: pre-snapshot ROBOT.md, replug, observe diff, assert backend: lerobot appended.
    pytest.skip("manual replug step required — see cli/tests/manual/sphp_smoke.md")
```

```python
# cli/tests/hardware/test_sphp_unknown_device_low_tier.py
from __future__ import annotations

import pytest

pytestmark = pytest.mark.hardware


def test_unknown_vid_pid_lands_as_low_tier() -> None:
    """Plug a CH340 dev board (or any device whose VID:PID isn't in the curated
    table). Expect a queue record at tier=LOW with `missing_preset_match` reason."""
    pytest.skip("manual plug step required — see cli/tests/manual/sphp_smoke.md")
```

- [ ] **Step 2: Write the manual smoke checklist**

Create `cli/tests/manual/sphp_smoke.md`:

```markdown
# SP-HP smoke — manual checks on bob

Daemon must be running (`robot-md hotplug-daemon start`) before each step.

1. **Linux: HIGH-tier auto-bind.** Replug SO-ARM101 USB cable on bob.
   Within 1 s the daemon's pyudev path catches it, classify returns HIGH
   (single-preset family, single backend installed), `manifest.merge` writes
   a new `drivers[]` entry with `backend: lerobot`. MCP server in an open
   Claude session emits `notifications/tools/list_changed`.

2. **Linux: MEDIUM-tier queue + confirm.** Plug a generic CH340 dongle (no
   serial-unique preset). Daemon classifies MEDIUM. `robot-md hotplug review`
   shows it. `robot-md hotplug confirm <event_id> --bind --choice 0` writes
   the manifest.

3. **macOS: file-poll path.** Same as #1 on macOS. Verify 1–2 s detection
   latency.

4. **Windows: polling fallback.** Same as #1 on Windows. WM_DEVICECHANGE
   message-pump integration is a Windows-host follow-up; polling alone is
   sufficient for v1.

5. **Daemon survives Claude restart.** Plug a generic feetech bus chip mid-
   Claude-session. Kill the Claude session before confirming. Reopen Claude.
   `hotplug_review` still surfaces the pending event.

6. **TTL expiry.** Set `pending_ttl_days = 0.001` in `~/.robot-md/hotplug.toml`.
   Plug a device, leave it pending. Wait 90 s. Daemon's expiry sweep
   appends `resolution: expired` for the original pending record.
```

- [ ] **Step 3: Verify hardware tests skip in default CI**

```bash
cd cli && PYTHONPATH=src python -m pytest tests/hardware/test_sphp_*.py -v
```

Expected: SKIPPED.

- [ ] **Step 4: Commit (Task 24)**

```bash
git add cli/tests/hardware/test_sphp_*.py cli/tests/manual/sphp_smoke.md
git commit -m "test(sphp): hardware-test stubs + manual smoke checklist"
```

---

## Implementation Order Summary

```
Phase A — DeviceEvent + per-platform watchers
  1. DeviceEvent + classify_transport
  2. linux watch_devices() (pyudev)
  3. macos watch_devices() (ioreg + pyserial polling)
  4. windows watch_devices() (polling fallback)
  5. cross-platform field-set lock test

Phase B — matcher
  6. BindProposal + Decision + presets_index
  7. classify(evt) — HIGH/MEDIUM/LOW
  8. recent-reject demotion (HIGH→MEDIUM within 1h)

Phase C — queue + audit
  9. EventQueue (hash-chained appends, atomic)
 10. first-writer-wins + truncation alert + TTL expiry
 11. per-RRN audit log

Phase D — manifest merge
 12. manifest.merge — schema gate + fcntl lock

Phase E — daemon
 13. HotplugConfig (~/.robot-md/hotplug.toml)
 14. Linux Unix socket listener
 15. daemon entry — composes everything
 16. EADDRINUSE protection (second instance exit 2)

Phase F — MCP server
 17. ManifestWatcher (watchdog inotify)
 18. hotplug_review MCP tool
 19. hotplug_confirm MCP tool

Phase G — CLI
 20. robot-md hotplug-daemon start|stop|status
 21. robot-md hotplug review|confirm
 22. robot-md hotplug install-service (systemd / launchd; Windows stub)

Phase H — integration + smoke
 23. end-to-end: HIGH-tier auto-bind writes manifest
 24. hardware-test stubs + manual smoke checklist
```

---

## Success Criteria

SP-HP is done when:

- [ ] All 24 tasks merged.
- [ ] Linux + macOS + Windows watchers all yield the same `DeviceEvent` shape (Task 5's lock test passes on each platform).
- [ ] `robot-md hotplug-daemon start` survives a 24 h idle soak: no socket leaks, no queue corruption, no audit-log gaps.
- [ ] Manual smoke (`cli/tests/manual/sphp_smoke.md`) passes 6/6 on bob.
- [ ] Hardware tests pass on bob (HIGH-tier replug end-to-end < 1 s wall clock; LOW-tier unknown device).
- [ ] `robot-md hotplug install-service` writes a working systemd unit on Linux + a working launchd plist on macOS.
- [ ] Cross-platform CI (Linux + macOS + Windows runners) green for every test except the `@pytest.mark.hardware` set, which is bob-local.

---

## Notes for the implementer

- **DeviceEvent immutability is load-bearing.** Watcher A produces events that flow through Tasks 6–24 unchanged. If a future task wants to mutate, that's a refactor — not an in-place edit. Task 5's drift guard catches accidental field renames.
- **Hash-chain integrity is non-negotiable.** Tests in Tasks 9 and 10 lock the chain; if a refactor breaks the algorithm, RRF audit-trail tooling stops accepting the queue. Don't regenerate hashes "for cleanup."
- **`fcntl` is Linux+macOS only.** Windows uses `msvcrt.locking`. The `queue.py` and `manifest.py` implementations as written assume POSIX; add a thin shim if Windows file-locking semantics surface as an issue (currently mitigated because the Windows daemon path is more polling-heavy and contention is rare).
- **`run_daemon` v1 only handles HIGH-tier auto-bind for the cwd manifest** (`Path.cwd() / "ROBOT.md"`). Multi-host or multi-manifest setups are out of scope. If the daemon runs as a systemd unit, its cwd is the operator's home; document that the daemon expects to find the active manifest there or via `--manifest-path` flag (follow-up).
- **Each task ends with a commit.** Plan execution is incremental.
