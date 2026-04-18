"""Tests for robot-md install-skill — ships the using-robot-md skill."""

from __future__ import annotations

import pytest

from robot_md.skill import SKILL_NAME, install, skill_content


def test_skill_content_is_non_empty():
    text = skill_content()
    assert text
    assert SKILL_NAME in text
    # The skill ships YAML frontmatter with the expected keys.
    assert text.startswith("---")
    assert "name: using-robot-md" in text
    assert "description:" in text


def test_install_writes_to_custom_dir(tmp_path):
    written = install(tmp_path)
    assert written.exists()
    assert written == tmp_path / SKILL_NAME / "SKILL.md"
    assert "using-robot-md" in written.read_text()


def test_install_refuses_overwrite_without_force(tmp_path):
    install(tmp_path)
    with pytest.raises(FileExistsError, match="already exists"):
        install(tmp_path)


def test_install_force_overwrites(tmp_path):
    first = install(tmp_path)
    # Corrupt the file.
    first.write_text("not the skill")
    # Re-install with force — should restore the real content.
    second = install(tmp_path, force=True)
    assert second == first
    assert "using-robot-md" in second.read_text()


def test_install_creates_parent_dirs(tmp_path):
    nested = tmp_path / "a" / "b" / "c"
    written = install(nested)
    assert written.exists()
    assert written.parent.parent == nested
