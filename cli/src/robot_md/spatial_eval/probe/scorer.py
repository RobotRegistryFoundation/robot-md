from __future__ import annotations

from typing import Callable

_SCORERS: dict[str, Callable[[dict, dict], tuple[bool, float]]] = {}


def register_scorer(unit_code: str, fn: Callable[[dict, dict], tuple[bool, float]]) -> None:
    _SCORERS[unit_code] = fn


def score_answer(unit_code: str, answer: dict, truth: dict) -> tuple[bool, float]:
    if unit_code not in _SCORERS:
        raise KeyError(f"no scorer registered for unit {unit_code!r}")
    return _SCORERS[unit_code](answer, truth)


def _bootstrap() -> None:
    """Force-import unit scorer modules so they self-register via register_scorer."""
    from robot_md.spatial_eval.probe import scorers  # noqa: F401
