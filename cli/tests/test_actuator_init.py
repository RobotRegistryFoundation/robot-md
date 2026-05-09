"""Tests for robot-md actuator init scaffolder."""

from __future__ import annotations

import json

import pytest

from robot_md.actuator import scaffold_actuator_package


def test_scaffold_creates_expected_tree(tmp_path):
    out = scaffold_actuator_package("my-actuator", tmp_path, author="test@example.com")
    pkg = out
    assert (pkg / "pyproject.toml").exists()
    assert (pkg / "README.md").exists()
    assert (pkg / "src" / "my_actuator" / "__init__.py").exists()
    assert (pkg / "src" / "my_actuator" / "actuator.py").exists()
    assert (pkg / "tests" / "__init__.py").exists()
    assert (pkg / "tests" / "test_actuator.py").exists()
    # Plugin sibling layout.
    assert (pkg / "claude-plugin" / ".claude-plugin" / "plugin.json").exists()
    assert (pkg / "claude-plugin" / "skills" / "using-my-actuator" / "SKILL.md").exists()
    assert (pkg / "claude-plugin" / "hooks" / "hooks.json").exists()
    # Bundled SKILL.md inside the installed Python package — so
    # `robot-md install-skill <pkg>` finds it via importlib.import_module.
    assert (pkg / "src" / "my_actuator" / "skills" / "using-my-actuator.SKILL.md").exists()


def test_scaffold_substitutes_kebab_snake_and_pascal(tmp_path):
    pkg = scaffold_actuator_package("my-cool-actuator", tmp_path, author="x@y.z")
    pyproject = (pkg / "pyproject.toml").read_text()
    # kebab name in [project.name]
    assert 'name = "my-cool-actuator"' in pyproject
    # snake-case dir
    assert (pkg / "src" / "my_cool_actuator").is_dir()
    # PascalCase class in actuator.py
    actuator_src = (pkg / "src" / "my_cool_actuator" / "actuator.py").read_text()
    assert "class MyCoolActuatorActuator:" in actuator_src
    # Entry-point line maps kebab→snake.actuator:Pascal
    assert "my-cool-actuator =" in pyproject
    assert "my_cool_actuator.actuator:MyCoolActuatorActuator" in pyproject


def test_scaffold_plugin_json_has_correct_metadata(tmp_path):
    pkg = scaffold_actuator_package("alpha", tmp_path, author="me@here")
    plugin = json.loads((pkg / "claude-plugin" / ".claude-plugin" / "plugin.json").read_text())
    assert plugin["name"] == "alpha"
    assert plugin["author"] == "me@here"
    assert plugin["version"] == "0.1.0"


def test_scaffold_skill_md_substitutes_only_name(tmp_path):
    """Other Jinja-style placeholders are left literal for Claude to fill."""
    pkg = scaffold_actuator_package("beta", tmp_path, author="x@y")
    skill_text = (pkg / "src" / "beta" / "skills" / "using-beta.SKILL.md").read_text()
    # `{{ name }}` substituted to `beta`.
    assert "name: using-beta" in skill_text
    # Other placeholders preserved.
    assert "{{ description }}" not in skill_text  # description IS substituted
    assert "{{ hardware_tag_1 }}" in skill_text   # hardware_tag is NOT substituted
    assert "{{ capability.tool_name }}" in skill_text


def test_scaffold_refuses_to_overwrite(tmp_path):
    scaffold_actuator_package("gamma", tmp_path, author="x@y")
    with pytest.raises(FileExistsError, match="already exists"):
        scaffold_actuator_package("gamma", tmp_path, author="x@y")


def test_scaffold_rejects_non_kebab_names(tmp_path):
    with pytest.raises(ValueError, match="kebab-case"):
        scaffold_actuator_package("My_Actuator", tmp_path, author="x@y")
    with pytest.raises(ValueError, match="kebab-case"):
        scaffold_actuator_package("my actuator", tmp_path, author="x@y")
