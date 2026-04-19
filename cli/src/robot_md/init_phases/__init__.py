"""Per-phase functions used by `robot-md init` orchestrator.

Each phase is independently callable and returns a uniform `PhaseResult`.
Phases never raise, except `phase_write_manifest` which is allowed to
raise on truly fatal I/O errors (disk full, refuse-to-overwrite).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PhaseStatus = Literal["ok", "skipped", "failed"]


@dataclass(frozen=True)
class PhaseResult:
    phase: str
    status: PhaseStatus
    message: str
    detail: dict | None


__all__ = ["PhaseResult", "PhaseStatus"]
