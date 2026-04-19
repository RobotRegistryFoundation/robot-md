"""MCP server context: loaded ROBOT.md + backend + estop flag."""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from robot_md.parser import ParsedRobotMd, parse_file
from robot_md.validate import VALID
from robot_md.validate import validate as validate_parsed


class EstopFlag:
    def __init__(self) -> None:
        self._set = False
        self._ts: float | None = None
        self._lock = threading.Lock()

    def set(self) -> float:
        with self._lock:
            self._set = True
            self._ts = time.time()
            return self._ts

    def clear(self) -> None:
        with self._lock:
            self._set = False
            self._ts = None

    def is_set(self) -> bool:
        with self._lock:
            return self._set

    def set_at(self) -> float | None:
        with self._lock:
            return self._ts


@dataclass
class McpContext:
    manifest_path: Path
    parsed: ParsedRobotMd
    spec: Any = None
    estop: EstopFlag = field(default_factory=EstopFlag)
    backend: Any = None
    exec_lock: threading.Lock = field(default_factory=threading.Lock)
    publisher: Any = None
    _command_watcher: Any = None


def load_context(manifest_path: Path) -> McpContext:
    """Parse + validate manifest, build RobotSpec, resolve backend, open it."""
    parsed = parse_file(manifest_path)
    result = validate_parsed(parsed)
    if result.code != VALID:
        raise RuntimeError(f"ROBOT.md validation failed: {result.errors}")

    from robot_md.backends.registry import BackendRegistry
    from robot_md.robot_spec import RobotSpec

    spec = RobotSpec.from_parsed(parsed)
    registry = BackendRegistry.from_entry_points()
    resolved = registry.resolve(spec)
    # Pick the first non-None backend (often the same backend claims both feetech + depthai).
    backend = next((b for b in resolved.values() if b is not None), None)
    # Spec §Python MCP server: server refuses to dispatch if
    # safety.max_joint_velocity_dps is missing. Fail fast rather than
    # silently leaving backend=None, which would be indistinguishable from
    # "no backend claims this protocol".
    if backend is not None:
        if spec.safety.max_joint_velocity_dps is None:
            raise RuntimeError(
                "refusing to open backend: safety.max_joint_velocity_dps is "
                "required but missing from ROBOT.md"
            )
        backend.open(spec)

    ctx = McpContext(
        manifest_path=manifest_path,
        parsed=parsed,
        spec=spec,
        backend=backend,
    )

    # Dashboard publisher + command watcher (opt-out via env)
    if os.environ.get("ROBOT_MD_DASHBOARD_DISABLED") != "1":
        from robot_md.dashboard.events import EventPublisher

        events_dir = Path(os.environ.get("HOME", str(Path.home()))) / ".robot-md"
        events_dir.mkdir(parents=True, exist_ok=True)
        ctx.publisher = EventPublisher(jsonl_path=events_dir / "events.jsonl")
        ctx.publisher.start()
        ctx._command_watcher = _start_command_watcher(ctx, events_dir / "commands.jsonl")

    return ctx


def _start_command_watcher(ctx, cmd_path: Path):
    """Spawn a daemon thread that polls commands.jsonl and dispatches."""
    import json as _json
    import logging as _logging
    import threading as _threading
    import time as _time

    log = _logging.getLogger("robot_md.mcp.command_watcher")

    # Initialize the tail position synchronously before returning so callers
    # (and tests) can append commands without racing the thread's startup.
    cmd_path.parent.mkdir(parents=True, exist_ok=True)
    cmd_path.touch(exist_ok=True)
    initial_pos = cmd_path.stat().st_size

    def _loop():
        pos = initial_pos
        while True:
            try:
                size = cmd_path.stat().st_size
            except FileNotFoundError:
                _time.sleep(0.2)
                continue
            if size < pos:
                pos = 0
            if size > pos:
                with cmd_path.open("r") as f:
                    f.seek(pos)
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = _json.loads(line)
                        except Exception:
                            log.warning("command_watcher: malformed line: %r", line)
                            continue
                        cmd = obj.get("cmd")
                        if cmd == "estop.set":
                            ctx.estop.set()
                            if ctx.publisher:
                                ctx.publisher.publish("estop.set", {"set": True})
                        elif cmd == "estop.clear":
                            ctx.estop.clear()
                            if ctx.publisher:
                                ctx.publisher.publish("estop.cleared", {"set": False})
                        elif cmd == "snapshot":
                            if ctx.backend is not None:
                                try:
                                    snap = ctx.backend.scene_describe()
                                    if ctx.publisher and snap and snap.frame:
                                        import base64 as _b64

                                        ctx.publisher.publish(
                                            "frame",
                                            {
                                                "png_b64": _b64.b64encode(snap.frame).decode(
                                                    "ascii"
                                                ),
                                                "width": 0,
                                                "height": 0,
                                            },
                                        )
                                except Exception as e:
                                    log.warning("command_watcher: snapshot failed: %s", e)
                        else:
                            log.warning("command_watcher: unknown cmd: %r", cmd)
                    pos = f.tell()
            _time.sleep(0.2)

    t = _threading.Thread(target=_loop, daemon=True, name="robot-md-cmd-watcher")
    t.start()
    return t
