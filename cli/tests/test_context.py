"""Tests for robot_md.context — Claude-ready text block emitter."""

from __future__ import annotations

from robot_md.context import emit_context
from robot_md.parser import parse_file


def test_context_starts_with_robot_identification(fixtures_dir):
    parsed = parse_file(fixtures_dir / "valid" / "minimal.ROBOT.md")
    text = emit_context(parsed)
    assert text.startswith("# Robot context"), text[:50]


def test_context_includes_robot_name(fixtures_dir):
    parsed = parse_file(fixtures_dir / "valid" / "minimal.ROBOT.md")
    text = emit_context(parsed)
    assert "test-bot" in text


def test_context_includes_capabilities_header(fixtures_dir):
    parsed = parse_file(fixtures_dir / "valid" / "minimal.ROBOT.md")
    text = emit_context(parsed)
    # minimal example has no capabilities; should note that explicitly
    assert "capabilit" in text.lower()


def test_context_includes_safety_header(fixtures_dir):
    parsed = parse_file(fixtures_dir / "valid" / "minimal.ROBOT.md")
    text = emit_context(parsed)
    assert "safety" in text.lower()


def test_context_embeds_body_prose(fixtures_dir):
    parsed = parse_file(fixtures_dir / "valid" / "minimal.ROBOT.md")
    text = emit_context(parsed)
    # The body of minimal.ROBOT.md has "Minimal test robot." — verify it shows up
    assert "Minimal test robot" in text


def test_context_ends_with_newline(fixtures_dir):
    parsed = parse_file(fixtures_dir / "valid" / "minimal.ROBOT.md")
    text = emit_context(parsed)
    assert text.endswith("\n")
