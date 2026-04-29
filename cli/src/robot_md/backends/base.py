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
    def empty(cls) -> SceneSnapshot:
        return cls(frame=None, detections=(), joint_state={}, ts=time.time())


class CapabilityBackend(ABC):
    name: str = "abstract"
    protocols: frozenset[str] = frozenset()
    read_only_capabilities: frozenset[str] = frozenset()

    @abstractmethod
    def open(self, spec: RobotSpec) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def capabilities(self) -> frozenset[str]: ...

    @abstractmethod
    def execute(
        self,
        capability: str,
        args: dict,
        *,
        dry_run: bool,
        estop: Any,
    ) -> ExecutionResult: ...

    def describe_capabilities(self) -> "list[Capability]":
        """Return rich metadata for each capability this backend declares.

        Default: walk self.capabilities(), look each up in
        cli/src/robot_md/schemas/capabilities.json for arg_schema +
        description; vendor capabilities not in the schema get
        arg_schema=None, description="".

        Adapters MAY override to provide richer vendor metadata
        (e.g., lerobot.teleop description, dynamixel.indirect_address
        arg shapes).
        """
        from robot_md.backends._capability_default import describe_default
        return describe_default(self.name, self.capabilities())

    def scene_describe(self) -> SceneSnapshot:
        return SceneSnapshot.empty()
