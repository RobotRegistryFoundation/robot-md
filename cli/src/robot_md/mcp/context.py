"""MCP server context: loaded ROBOT.md + backend + estop flag."""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from robot_md.mcp.invocation_log import InvocationLog
from robot_md.mcp.invocation_record import InvocationRecord
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

    def __init__(self, ctx: McpContext, inner: Any) -> None:
        self._ctx = ctx
        self._inner = inner

    def __getattr__(self, name: str) -> Any:
        # Forward any non-overridden attribute (e.g. `stop`, `jsonl_path`,
        # `ws_port`) to the wrapped publisher so callers that pre-date the
        # wrapper don't break. Only `publish` is intercepted for stamping
        # and fan-out; everything else passes through transparently.
        return getattr(self._inner, name)

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
            rid for rid, v in self._ctx._pending_calls.items() if now - v["ts"] > _PENDING_TTL_S
        ]
        for rid in expired:
            self._ctx._pending_calls.pop(rid, None)


def _install_publisher_fanout(ctx: McpContext) -> None:
    """Wrap ctx.publisher in place. Safe to call multiple times (idempotent)."""
    if isinstance(ctx.publisher, _PublisherFanoutWrapper):
        return
    if ctx.publisher is None:
        return
    ctx.publisher = _PublisherFanoutWrapper(ctx, ctx.publisher)


#: Opt in to opening the camera inside the MCP server, for `vision_find` and
#: `discover`'s capture/detect. Off by default: robot-md-gateway's camera
#: actuator (oak-d-actuator) may hold the camera, and a DepthAI device has one
#: owner at a time. Set it only where nothing else uses the camera.
ENV_OPEN_CAMERA = "ROBOT_MD_MCP_OPEN_CAMERA"


def load_context(manifest_path: Path, *, open_servo_bus: bool = False) -> McpContext:
    """Parse + validate manifest, build RobotSpec, resolve the backend.

    The MCP server opens no device by default. Motion goes through
    robot-md-gateway, which holds the robot's motor port (so-arm101-actuator
    claims it exclusively at startup), and opening that port here would race
    the gateway for it. The backend is resolved but not opened, so its
    capability metadata is available and nothing is held.

    With $ROBOT_MD_MCP_OPEN_CAMERA=1 the server opens the backend's cameras
    only (`CapabilityBackend.open_perception`), never its motors.

    `open_servo_bus=True` opens the whole backend, motors included. It is for
    the operator CLI verbs that read the bus with a person at the machine
    (`robot-md pose teach`). The MCP server never passes it.
    """
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
            if open_servo_bus:
                backend.open(spec)
            elif os.environ.get(ENV_OPEN_CAMERA) == "1":
                backend.open_perception(spec)
        except (ImportError, OSError, RuntimeError) as e:
            # Optional hardware dep not installed (ImportError on scservo_sdk
            # / depthai), declared device not openable (OSError /
            # SerialException — pyserial raises SerialException, a subclass
            # of IOError/OSError), or backend's own open-time validation
            # failed (RuntimeError). Degrade to a backend-less context so
            # render / validate / read-only tools still work. Motion does not
            # depend on the backend: it goes to robot-md-gateway.
            import logging as _logging

            _logging.getLogger("robot_md.mcp").warning(
                "backend open failed (%s); running without an open backend", e
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
        _install_publisher_fanout(ctx)
        ctx._command_watcher = _start_command_watcher(ctx, events_dir / "commands.jsonl")

        # Backfill the InvocationLog from the prior JSONL content for this
        # manifest only. Never raises — missing/malformed file yields empty.
        ctx.invocation_log.backfill_from_jsonl(
            events_dir / "events.jsonl",
            manifest_path=str(manifest_path),
            n=100,
        )

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
                        # The dashboard's stop and clear take the same path as
                        # the MCP tools: the stop goes to robot-md-gateway's
                        # declared stop, and a clear is asked of the gateway at
                        # the commission tier. Anyone who can write this file
                        # can send these, so neither is trusted any further
                        # than the MCP tools are.
                        if cmd == "estop.set":
                            from robot_md.mcp.tools.estop import estop_tool

                            try:
                                estop_tool(ctx)
                            except Exception as e:
                                log.warning("command_watcher: estop failed: %s", e)
                        elif cmd == "estop.clear":
                            from robot_md.mcp.tools.estop import estop_clear_tool

                            try:
                                estop_clear_tool(ctx)
                            except Exception as e:
                                log.warning("command_watcher: estop clear failed: %s", e)
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
