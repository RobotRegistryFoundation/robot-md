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
