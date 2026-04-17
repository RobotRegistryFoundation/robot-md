"""Tests for robot_md.render — strips prose, emits pure YAML."""

from __future__ import annotations

import yaml

from robot_md.parser import parse_file
from robot_md.render import render_yaml


def test_render_returns_valid_yaml(fixtures_dir):
    parsed = parse_file(fixtures_dir / "valid" / "minimal.ROBOT.md")
    text = render_yaml(parsed)
    doc = yaml.safe_load(text)
    assert isinstance(doc, dict)


def test_render_preserves_frontmatter_exactly(fixtures_dir):
    parsed = parse_file(fixtures_dir / "valid" / "minimal.ROBOT.md")
    text = render_yaml(parsed)
    doc = yaml.safe_load(text)
    assert doc == parsed.frontmatter


def test_render_has_no_markdown_delimiters(fixtures_dir):
    parsed = parse_file(fixtures_dir / "valid" / "minimal.ROBOT.md")
    text = render_yaml(parsed)
    assert "---" not in text.split("\n")[0], "no frontmatter delimiters in output"
    assert "# test-bot" not in text, "prose body not included"


def test_render_uses_block_style(fixtures_dir):
    """Flow style is less readable for configs; prefer block."""
    parsed = parse_file(fixtures_dir / "valid" / "minimal.ROBOT.md")
    text = render_yaml(parsed)
    # Block style uses colons + indentation, not inline dicts
    assert "metadata:\n" in text
