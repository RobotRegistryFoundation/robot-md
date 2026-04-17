"""Tests for the frontmatter + body parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from robot_md.parser import ParsedRobotMd, ParseError, parse_file, parse_text


def _read(path: Path) -> str:
    return path.read_text()


def test_parse_minimal_valid(fixtures_dir):
    path = fixtures_dir / "valid" / "minimal.ROBOT.md"
    result = parse_file(path)
    assert isinstance(result, ParsedRobotMd)
    assert result.frontmatter["metadata"]["robot_name"] == "test-bot"
    assert result.frontmatter["rcan_version"] == "3.0"
    assert "# test-bot" in result.body
    assert "## Safety Gates" in result.body


def test_parse_text_vs_file_agree(fixtures_dir):
    path = fixtures_dir / "valid" / "minimal.ROBOT.md"
    from_file = parse_file(path)
    from_text = parse_text(_read(path))
    assert from_file.frontmatter == from_text.frontmatter
    assert from_file.body == from_text.body


def test_parse_no_frontmatter_raises(fixtures_dir):
    path = fixtures_dir / "invalid" / "no-frontmatter.md"
    with pytest.raises(ParseError, match="frontmatter"):
        parse_file(path)


def test_parse_bad_yaml_raises(fixtures_dir):
    path = fixtures_dir / "invalid" / "bad-yaml.ROBOT.md"
    with pytest.raises(ParseError, match="YAML"):
        parse_file(path)


def test_parse_missing_file_raises(tmp_path):
    with pytest.raises(ParseError, match="not found"):
        parse_file(tmp_path / "does-not-exist.md")


def test_parsed_has_source_path(fixtures_dir):
    path = fixtures_dir / "valid" / "minimal.ROBOT.md"
    result = parse_file(path)
    assert result.source_path == path


def test_parse_text_has_no_source_path(fixtures_dir):
    path = fixtures_dir / "valid" / "minimal.ROBOT.md"
    result = parse_text(_read(path))
    assert result.source_path is None
