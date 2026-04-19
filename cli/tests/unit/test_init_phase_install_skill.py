"""Unit tests for phase_install_skill."""

from __future__ import annotations

from unittest.mock import patch


def test_ok_returns_installed_path(tmp_path):
    from robot_md.init_phases import phase_install_skill

    skills_dir = tmp_path / "skills"
    target = skills_dir / "using-robot-md" / "SKILL.md"
    with patch("robot_md.init_phases.install_skill.skill_install", return_value=target) as inst:
        result = phase_install_skill(dest_root=skills_dir)

    assert result.status == "ok"
    assert result.detail and str(target) == result.detail.get("path")
    assert inst.call_args.kwargs.get("dest_root") == skills_dir


def test_already_installed_returns_ok_with_note(tmp_path):
    from robot_md.init_phases import phase_install_skill

    skills_dir = tmp_path / "skills"

    def raise_exists(*_, **__):
        raise FileExistsError("already there")

    with patch("robot_md.init_phases.install_skill.skill_install", side_effect=raise_exists):
        result = phase_install_skill(dest_root=skills_dir)

    assert result.status == "ok"
    assert result.detail and result.detail.get("already_installed") is True


def test_permission_error_returns_failed(tmp_path):
    from robot_md.init_phases import phase_install_skill

    with patch(
        "robot_md.init_phases.install_skill.skill_install",
        side_effect=PermissionError("nope"),
    ):
        result = phase_install_skill(dest_root=tmp_path / "skills")

    assert result.status == "failed"
    assert "permission" in result.message.lower() or "nope" in result.message.lower()


def test_filenotfound_skill_content_returns_failed(tmp_path):
    from robot_md.init_phases import phase_install_skill

    with patch(
        "robot_md.init_phases.install_skill.skill_install",
        side_effect=FileNotFoundError("SKILL.md missing from wheel"),
    ):
        result = phase_install_skill(dest_root=tmp_path / "skills")

    assert result.status == "failed"
