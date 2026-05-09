"""robot-md install-skill — copy the bundled `using-robot-md` skill into
the operator's skill directory.

Targets [superpowers](https://github.com/obra/superpowers) (and any other
skill-aware harness) that loads skills from `~/.claude/skills/`. Once
installed, Claude Code auto-invokes the skill whenever it recognizes
robot-related intent in a session — "what can this robot do", "is it
safe to X", "pose the arm at zero", etc.

The canonical source ships in the `robot-md` Claude Code plugin at
https://github.com/RobotRegistryFoundation/robot-md-mcp (skills/using-robot-md/).
A copy is bundled in this wheel under `robot_md/skills/using-robot-md.SKILL.md`
so `robot-md install-skill` can install it without network access.
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from pathlib import Path

SKILL_NAME = "using-robot-md"
_BUNDLED = Path(__file__).parent / "skills" / "using-robot-md.SKILL.md"


def skill_content() -> str:
    """Return the canonical SKILL.md content from the wheel-bundled copy.

    Raises FileNotFoundError if the bundled file is missing (should not
    happen in a correctly-built wheel or editable install).
    """
    if _BUNDLED.exists():
        return _BUNDLED.read_text()
    raise FileNotFoundError(f"could not locate {SKILL_NAME}.SKILL.md in the wheel ({_BUNDLED})")


def default_skills_dir() -> Path:
    """Return the default user-level skills directory (`~/.claude/skills`)."""
    return Path.home() / ".claude" / "skills"


def install(
    dest_root: Path | None = None,
    *,
    force: bool = False,
) -> Path:
    """Install the skill into `<dest_root>/using-robot-md/SKILL.md`.

    Returns the full path written. If the target file already exists and
    `force` is False, raises FileExistsError.
    """
    dest_root = dest_root or default_skills_dir()
    target_dir = dest_root / SKILL_NAME
    target_file = target_dir / "SKILL.md"

    if target_file.exists() and not force:
        raise FileExistsError(f"{target_file} already exists — pass --force to overwrite")

    target_dir.mkdir(parents=True, exist_ok=True)
    target_file.write_text(skill_content())
    return target_file


def iter_skills_for_package(package_name: str) -> Iterator[Path]:
    """Yield each `<package>/skills/*.SKILL.md` file in an installed package.

    Resolves `package_name` via importlib (must be importable; raises
    ModuleNotFoundError otherwise). Empty iterator if the package has no
    `skills/` subdir.
    """
    mod = importlib.import_module(package_name)
    if not mod.__file__:
        return
    pkg_dir = Path(mod.__file__).parent
    skills_dir = pkg_dir / "skills"
    if not skills_dir.is_dir():
        return
    yield from sorted(skills_dir.glob("*.SKILL.md"))


def install_package_skills(package_name: str, dest_root: Path) -> list[Path]:
    """Install all skills from `<package>/skills/` into `<dest_root>/<package>/`.

    REPLACE-on-conflict (OQ-A): existing files at the target are overwritten.
    Returns the list of written paths.
    """
    pkg_dest = dest_root / package_name
    pkg_dest.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for skill_path in iter_skills_for_package(package_name):
        target = pkg_dest / skill_path.name
        target.write_text(skill_path.read_text())
        written.append(target)
    return written


def iter_all_installed_skills() -> Iterator[tuple[str, Path]]:
    """Yield (package_name, skill_path) for every Python package on
    sys.path that ships a `skills/*.SKILL.md`.

    Walks installed-distribution metadata via `importlib.metadata` rather
    than glob-walking sys.path, so wheels are visible. For editable installs
    (which may not have a complete RECORD), attempts direct import and
    enumeration as a fallback. The bundled `robot_md` is always present
    since it ships `robot_md/skills/using-robot-md.SKILL.md`.
    """
    from importlib.metadata import distributions

    seen: set[str] = set()
    for dist in distributions():
        # `dist.files` is None for distributions without RECORD; editable
        # installs often lack a complete RECORD, so fallback to direct import.
        files = dist.files or []
        # Each `dist.files` entry is a relative path under site-packages.
        # The top-level package name is the first path segment.
        candidates = {
            f.parts[0]
            for f in files
            if len(f.parts) >= 3
            and f.parts[1] == "skills"
            and f.parts[-1].endswith(".SKILL.md")
        }
        # For editable installs with empty files, try the top-level package name.
        if not candidates and dist.name:
            # Normalize distribution name to package name (e.g., 'robot-md' -> 'robot_md').
            pkg_candidate = dist.name.replace("-", "_")
            candidates = {pkg_candidate}

        for pkg in candidates:
            if pkg in seen:
                continue
            seen.add(pkg)
            try:
                for skill_path in iter_skills_for_package(pkg):
                    yield pkg, skill_path
            except ModuleNotFoundError:
                # Distribution lists a package that isn't importable.
                # Skip rather than crash enumeration.
                continue
