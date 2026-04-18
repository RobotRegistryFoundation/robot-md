"""Planning primitives shared by prompt, decompose, and MCP tool."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlanStep:
    capability: str
    args: dict
    confidence: float


@dataclass(frozen=True)
class Plan:
    steps: tuple[PlanStep, ...]
    raw_response: dict


class PlanError(Exception):
    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail
