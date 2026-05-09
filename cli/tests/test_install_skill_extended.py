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


def test_install_package_skills_writes_each_skill(tmp_path, monkeypatch):
    from robot_md.skill import install_package_skills

    _make_fake_package(
        tmp_path, "fake_actuator2",
        {
            "using-fake-actuator2.SKILL.md": "---\nname: using-fake-actuator2\n---\nbody",
            "extra.SKILL.md": "---\nname: extra\n---\nbody",
        },
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    dest = tmp_path / "skills"
    written = install_package_skills("fake_actuator2", dest)

    assert len(written) == 2
    names = {p.name for p in written}
    assert "using-fake-actuator2.SKILL.md" in names
    assert "extra.SKILL.md" in names
    # Files land under <dest>/<package>/<filename>.
    for p in written:
        assert p.parent == dest / "fake_actuator2"
        assert p.exists()


def test_install_package_skills_replace_on_conflict(tmp_path, monkeypatch):
    """OQ-A resolution from spec: REPLACE on conflict (single file per skill name)."""
    from robot_md.skill import install_package_skills

    _make_fake_package(
        tmp_path, "fake_actuator3",
        {"using-fake-actuator3.SKILL.md": "---\nname: using-fake-actuator3\n---\nv1"},
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    dest = tmp_path / "skills"
    install_package_skills("fake_actuator3", dest)
    # Re-import after editing — wipe import cache so re-read picks up new content.
    src = tmp_path / "fake_actuator3" / "skills" / "using-fake-actuator3.SKILL.md"
    src.write_text("---\nname: using-fake-actuator3\n---\nv2")

    install_package_skills("fake_actuator3", dest)
    assert (dest / "fake_actuator3" / "using-fake-actuator3.SKILL.md").read_text().endswith("v2")


def test_iter_all_installed_skills_includes_robot_md_self():
    """Sanity: the bundled using-robot-md skill should always be enumerable."""
    from robot_md.skill import iter_all_installed_skills

    entries = list(iter_all_installed_skills())
    # `robot_md` itself ships using-robot-md.SKILL.md.
    pkg_names = {pkg for pkg, _path in entries}
    assert "robot_md" in pkg_names
