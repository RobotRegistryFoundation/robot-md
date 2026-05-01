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


# ── Issue #32: directory paths resolve to <dir>/ROBOT.md ───────────────────
# Every CLI command that takes a manifest path (compliance status, render,
# emit-*, validate, ...) goes through parse_file. Pushing the dir→ROBOT.md
# resolution here makes `robot-md compliance status .` and equivalents
# work as users naturally expect.


def test_parse_directory_resolves_to_robot_md(tmp_path):
    """A directory containing ROBOT.md is accepted; parses the manifest inside."""
    (tmp_path / "ROBOT.md").write_text(
        "---\nrcan_version: '3.0'\nmetadata:\n  robot_name: dirtest\n---\n# dirtest\n"
    )
    result = parse_file(tmp_path)
    assert result.frontmatter["metadata"]["robot_name"] == "dirtest"
    assert result.source_path == tmp_path / "ROBOT.md"


def test_parse_dot_directory_resolves(tmp_path, monkeypatch):
    """`robot-md compliance status .` — the original failure mode in #32."""
    (tmp_path / "ROBOT.md").write_text(
        "---\nrcan_version: '3.0'\nmetadata:\n  robot_name: dottest\n---\n# dottest\n"
    )
    monkeypatch.chdir(tmp_path)
    result = parse_file(Path("."))
    assert result.frontmatter["metadata"]["robot_name"] == "dottest"


def test_parse_directory_without_robot_md_raises(tmp_path):
    """A directory with no ROBOT.md inside surfaces a clear error message."""
    with pytest.raises(ParseError, match=r"ROBOT\.md"):
        parse_file(tmp_path)


def test_parse_explicit_file_in_directory_still_works(tmp_path):
    """Passing the explicit path inside a directory keeps working unchanged."""
    manifest = tmp_path / "ROBOT.md"
    manifest.write_text(
        "---\nrcan_version: '3.0'\nmetadata:\n  robot_name: explicit\n---\n# explicit\n"
    )
    result = parse_file(manifest)
    assert result.frontmatter["metadata"]["robot_name"] == "explicit"
    assert result.source_path == manifest
