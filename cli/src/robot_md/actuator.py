"""robot-md actuator — scaffolder for production actuator packages.

Plan 2 ships `actuator init`. Plans 3+ will add `actuator search` and
`actuator publish` (registry primitive).
"""

from __future__ import annotations

import re
from importlib import resources
from pathlib import Path

_KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def _validate_name(name: str) -> None:
    if not _KEBAB_RE.match(name):
        raise ValueError(
            f"package name {name!r} must be kebab-case (lowercase letters, digits, single hyphens)"
        )


def _kebab_to_snake(name: str) -> str:
    return name.replace("-", "_")


def _kebab_to_pascal(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("-"))


def _read_template(name: str) -> str:
    """Read a packaged template file from `robot_md/templates/actuator/`."""
    return resources.files("robot_md.templates").joinpath("actuator", name).read_text()


def _render(
    template: str,
    *,
    name: str,
    name_underscored: str,
    NameClass: str,
    description: str,
    author: str,
) -> str:
    """Substitute scaffold-time placeholders. Other `{{ ... }}` left literal."""
    return (
        template.replace("{{ name }}", name)
        .replace("{{ name_underscored }}", name_underscored)
        .replace("{{ NameClass }}", NameClass)
        .replace("{{ description }}", description)
        .replace("{{ author }}", author)
    )


def scaffold_actuator_package(
    name: str,
    parent_dir: Path,
    *,
    author: str,
    description: str = "TODO: one-line description of what this actuator drives.",
) -> Path:
    """Create a production actuator package skeleton at `<parent_dir>/<name>/`.

    Returns the package root path.
    """
    _validate_name(name)
    snake = _kebab_to_snake(name)
    pascal = _kebab_to_pascal(name)

    pkg_root = parent_dir / name
    if pkg_root.exists():
        raise FileExistsError(f"{pkg_root} already exists")

    src_dir = pkg_root / "src" / snake
    src_skills_dir = src_dir / "skills"
    tests_dir = pkg_root / "tests"
    plugin_dir = pkg_root / "claude-plugin" / ".claude-plugin"
    plugin_skills_dir = pkg_root / "claude-plugin" / "skills" / f"using-{name}"
    plugin_hooks_dir = pkg_root / "claude-plugin" / "hooks"

    for d in (src_dir, src_skills_dir, tests_dir, plugin_dir, plugin_skills_dir, plugin_hooks_dir):
        d.mkdir(parents=True, exist_ok=True)

    common = dict(
        name=name,
        name_underscored=snake,
        NameClass=pascal,
        description=description,
        author=author,
    )

    # Top-level files.
    (pkg_root / "pyproject.toml").write_text(
        _render(_read_template("pyproject.toml.tmpl"), **common)
    )
    (pkg_root / "README.md").write_text(_render(_read_template("README.md.tmpl"), **common))

    # Python source.
    (src_dir / "__init__.py").write_text("")
    (src_dir / "actuator.py").write_text(_render(_read_template("src_actuator.py.tmpl"), **common))

    # Tests.
    (tests_dir / "__init__.py").write_text("")
    (tests_dir / "test_actuator.py").write_text(
        _render(_read_template("test_actuator.py.tmpl"), **common)
    )

    # Claude-plugin sibling.
    (plugin_dir / "plugin.json").write_text(_render(_read_template("plugin.json.tmpl"), **common))
    (plugin_skills_dir / "SKILL.md").write_text(_render(_read_template("skill.md.tmpl"), **common))
    (plugin_hooks_dir / "hooks.json").write_text(
        _render(_read_template("hooks.json.tmpl"), **common)
    )

    # Bundled SKILL.md inside the importable Python package — so
    # `robot-md install-skill <pkg>` (Plan 2 Task 7) finds it via
    # `importlib.import_module(<pkg>).__file__.parent / "skills"`.
    (src_skills_dir / f"using-{name}.SKILL.md").write_text(
        _render(_read_template("skill.md.tmpl"), **common)
    )

    return pkg_root
