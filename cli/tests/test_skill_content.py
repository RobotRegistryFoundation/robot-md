"""Tests that the bundled SKILL.md ships the expected guidance sections."""

from __future__ import annotations

from pathlib import Path

SKILL = (
    Path(__file__).resolve().parents[1] / "src" / "robot_md" / "skills" / "using-robot-md.SKILL.md"
)


def test_skill_contains_search_before_write_section():
    src = SKILL.read_text()
    assert "Before writing an actuator from scratch" in src
    assert "robot-md actuator search" in src
    assert "robot-md actuator publish" in src
