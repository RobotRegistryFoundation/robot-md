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
from robot_md.mcp.invocation_log import InvocationLog
from robot_md.mcp.invocation_record import InvocationRecord


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
    invocation_log: InvocationLog = field(default_factory=lambda: InvocationLog(maxlen=100))
    _pending_calls: dict[str, dict] = field(default_factory=dict)
    _pending_lock: threading.Lock = field(default_factory=threading.Lock)


_PENDING_TTL_S = 60.0


class _PublisherFanoutWrapper:
    """Wraps an EventPublisher-like object to: (a) stamp manifest_path into
    every event's data; (b) pair tool.call/tool.result events by request_id
    and append an InvocationRecord to ctx.invocation_log on each pair.

    The wrapper is installed in-place on ctx (ctx.publisher becomes this
    wrapper); all existing `ctx.publisher.publish(...)` call sites are
    unchanged.
    """

    def __init__(self, ctx: "McpContext", inner: Any) -> None:
        self._ctx = ctx
        self._inner = inner

    def publish(self, kind: str, data: dict) -> None:
        # Copy to avoid mutating the caller's dict; stamp manifest_path.
        stamped = dict(data)
        stamped["manifest_path"] = str(self._ctx.manifest_path)

        # Fan out paired tool.call / tool.result into the invocation log
        # before forwarding — the JSONL write is what other consumers see
        # anyway, so ordering between log append and JSONL write does not
        # matter for correctness. Fan-out failures must never block the
        # JSONL write: a dashboard event is more important than a ring
        # bookkeeping slot.
        try:
            self._maybe_pair_and_log(kind, stamped)
        except Exception:
            import logging
            logging.getLogger(__name__).exception("fanout: log append failed")
        self._inner.publish(kind, stamped)

    def _maybe_pair_and_log(self, kind: str, data: dict) -> None:
        if kind == "tool.call":
            rid = data.get("request_id")
            if not rid:
                return
            with self._ctx._pending_lock:
                self._sweep_expired_locked()
                self._ctx._pending_calls[rid] = {"ts": time.time(), "data": data, "kind": kind}
            return
        if kind != "tool.result":
            return
        rid = data.get("request_id")
        if not rid:
            return
        with self._ctx._pending_lock:
            call_entry = self._ctx._pending_calls.pop(rid, None)
        if call_entry is None:
            return
        call_evt = {"kind": "tool.call", "ts": call_entry["ts"], "data": call_entry["data"]}
        result_evt = {"kind": "tool.result", "ts": time.time(), "data": data}
        try:
            record = InvocationRecord.from_event_pair(call_evt, result_evt)
        except Exception:
            return
        self._ctx.invocation_log.append(record)

    def _sweep_expired_locked(self) -> None:
        now = time.time()
        expired = [
            rid for rid, v in self._ctx._pending_calls.items()
            if now - v["ts"] > _PENDING_TTL_S
        ]
        for rid in expired:
            self._ctx._pending_calls.pop(rid, None)


def _install_publisher_fanout(ctx: "McpContext") -> None:
    """Wrap ctx.publisher in place. Safe to call multiple times (idempotent)."""
    if isinstance(ctx.publisher, _PublisherFanoutWrapper):
        return
    if ctx.publisher is None:
        return
    ctx.publisher = _PublisherFanoutWrapper(ctx, ctx.publisher)


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
        try:
            backend.open(spec)
        except ImportError as e:
            # Optional hardware dep not installed (e.g. feetech_servo_sdk,
            # depthai). Degrade to a backend-less context so render/validate
            # still work. execute_capability will return no_backend.
            import logging as _logging

            _logging.getLogger("robot_md.mcp").warning(
                "backend.open failed due to missing dep (%s); running without backend", e
            )
            backend = None

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
