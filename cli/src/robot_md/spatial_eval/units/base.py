from __future__ import annotations

from typing import Any, Protocol


class Unit(Protocol):
    """Protocol every unit module satisfies via module-level attributes."""

    code: str  # e.g., "O1"
    description: str  # human-readable summary

    @staticmethod
    def parse_answer(raw: dict) -> "ProbeAnswer": ...

    @staticmethod
    def execute_pass(trial_outcome: dict) -> tuple[bool, str]: ...


class ProbeAnswer(dict):
    """Marker subclass; canonical shape is unit-specific."""


REGISTRY: dict[str, Any] = {}


def register(unit_module: Any) -> Any:
    """Decorator-or-call to register a unit module by its `.code` attribute."""
    code = getattr(unit_module, "code")
    REGISTRY[code] = unit_module
    return unit_module


def get_unit(code: str) -> Any:
    return REGISTRY[code]
