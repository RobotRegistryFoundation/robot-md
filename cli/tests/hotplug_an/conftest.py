"""Sandboxed harness for skill-text contract tests.

Provides a SkillTextHarness that loads the bundled CLI mirror of
using-robot-md.SKILL.md and exposes a regex-level rule-presence checker.
The harness is deliberately scope-limited: it asserts that the skill
text contains the rules a real Claude session would read, NOT that
Claude actually follows them. Live-model behavior is verified by the
manual smoke checklist at cli/tests/manual/span_smoke.md (Task 12).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

_SKILL_PATH = Path(__file__).parents[2] / "src" / "robot_md" / "skills" / "using-robot-md.SKILL.md"


@dataclass
class SkillTextHarness:
    skill_text: str

    def has_rule(self, *substrings: str) -> bool:
        return all(s in self.skill_text for s in substrings)


@pytest.fixture
def harness() -> SkillTextHarness:
    return SkillTextHarness(skill_text=_SKILL_PATH.read_text())
