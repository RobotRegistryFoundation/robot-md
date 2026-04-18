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
    estop: EstopFlag = field(default_factory=EstopFlag)
    backend: Any = None
    exec_lock: threading.Lock = field(default_factory=threading.Lock)


def load_context(manifest_path: Path) -> McpContext:
    """Parse + validate the manifest. Raise RuntimeError on any fatal error."""
    parsed = parse_file(manifest_path)
    result = validate_parsed(parsed)
    if result.code != VALID:
        raise RuntimeError(f"ROBOT.md validation failed: {result.errors}")
    return McpContext(manifest_path=manifest_path, parsed=parsed)
