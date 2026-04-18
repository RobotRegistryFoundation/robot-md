"""Abstract CapabilityBackend interface."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from robot_md.robot_spec import RobotSpec


@dataclass(frozen=True)
class ExecutionEvent:
    kind: str
    data: dict[str, Any]


@dataclass(frozen=True)
class ExecutionResult:
    status: str
    trajectory: list[dict] | None
    events: list[ExecutionEvent]
    error: dict | None


@dataclass(frozen=True)
class SceneSnapshot:
    frame: bytes | None
    detections: tuple[dict, ...]
    joint_state: dict[str, float]
    ts: float

    @classmethod
    def empty(cls) -> "SceneSnapshot":
        return cls(frame=None, detections=(), joint_state={}, ts=time.time())


class CapabilityBackend(ABC):
    name: str = "abstract"
    protocols: frozenset[str] = frozenset()

    @abstractmethod
    def open(self, spec: RobotSpec) -> None:
        ...

    @abstractmethod
    def close(self) -> None:
        ...

    @abstractmethod
    def capabilities(self) -> frozenset[str]:
        ...

    @abstractmethod
    def execute(
        self,
        capability: str,
        args: dict,
        *,
        dry_run: bool,
        estop: Any,
    ) -> ExecutionResult:
        ...

    def scene_describe(self) -> SceneSnapshot:
        return SceneSnapshot.empty()
