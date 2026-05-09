"""Tests for extended `robot-md install-skill <package>` and --list flag."""

from __future__ import annotations

from pathlib import Path

import pytest


def _make_fake_package(tmp_path: Path, package_name: str, skills: dict[str, str]) -> Path:
    """Create an importable package on tmp_path with skills/ subdir.

    Returns the package source dir (caller adds to sys.path).
    """
    pkg_dir = tmp_path / package_name
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")
    skills_dir = pkg_dir / "skills"
    skills_dir.mkdir()
    for skill_filename, content in skills.items():
        (skills_dir / skill_filename).write_text(content)
    return pkg_dir


def test_iter_skills_for_package_returns_paths(tmp_path, monkeypatch):
    from robot_md.skill import iter_skills_for_package

    _make_fake_package(
        tmp_path, "fake_actuator",
        {"using-fake-actuator.SKILL.md": "---\nname: using-fake-actuator\n---\nbody"},
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    paths = list(iter_skills_for_package("fake_actuator"))
    assert len(paths) == 1
    assert paths[0].name == "using-fake-actuator.SKILL.md"
    assert paths[0].read_text().startswith("---")


def test_iter_skills_for_package_no_skills_dir_returns_empty(tmp_path, monkeypatch):
    from robot_md.skill import iter_skills_for_package

    pkg_dir = tmp_path / "no_skills_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")
    monkeypatch.syspath_prepend(str(tmp_path))

    assert list(iter_skills_for_package("no_skills_pkg")) == []


def test_iter_skills_for_package_unknown_package_raises(monkeypatch):
    from robot_md.skill import iter_skills_for_package

    with pytest.raises(ModuleNotFoundError):
        list(iter_skills_for_package("definitely_not_installed_xyz"))
