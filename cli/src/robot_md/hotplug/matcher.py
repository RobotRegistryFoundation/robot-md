"""Hot-plug event tier classifier. classify() lands in Task 7."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from robot_md.backends.capability import Capability


@dataclass(frozen=True)
class BindProposal:
    rrn: str | None
    driver_id_suggestion: str
    backend_name: str
    preset_name: str | None
    capability_preview: list[Capability]
    inferred_fields: dict


@dataclass(frozen=True)
class Decision:
    tier: Literal["HIGH", "MEDIUM", "LOW"]
    unambiguous: bool
    bind_proposal: BindProposal | None
    alternatives: list[BindProposal] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
