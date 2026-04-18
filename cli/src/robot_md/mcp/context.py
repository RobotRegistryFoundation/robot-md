"""MCP server context: loaded ROBOT.md + backend + estop flag."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from robot_md.parser import ParsedRobotMd, parse_file
from robot_md.validate import VALID, validate as validate_parsed


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

    return McpContext(
        manifest_path=manifest_path,
        parsed=parsed,
        spec=spec,
        backend=backend,
    )
