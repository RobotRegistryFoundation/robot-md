"""robot-md install-skill — copy the bundled `using-robot-md` skill into
the operator's skill directory.

Targets [superpowers](https://github.com/obra/superpowers) (and any other
skill-aware harness) that loads skills from `~/.claude/skills/`. Once
installed, Claude Code auto-invokes the skill whenever it recognizes
robot-related intent in a session — "what can this robot do", "is it
safe to X", "pose the arm at zero", etc.

Canonical source lives at `integrations/claude-code-skill/SKILL.md` in
the robot-md repo; a copy is bundled in the wheel under
`robot_md/skills/using-robot-md.SKILL.md` so the CLI can install it
without network access.
"""

from __future__ import annotations

from pathlib import Path

SKILL_NAME = "using-robot-md"
_BUNDLED = Path(__file__).parent / "skills" / "using-robot-md.SKILL.md"
_REPO_FALLBACK = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "integrations"
    / "claude-code-skill"
    / "SKILL.md"
)


def skill_content() -> str:
    """Return the canonical SKILL.md content.

    Prefers the wheel-bundled copy; falls back to the repo tree (useful
    when running editable installs where `src/robot_md/skills/` was not
    synced). Raises FileNotFoundError if neither is present.
    """
    if _BUNDLED.exists():
        return _BUNDLED.read_text()
    if _REPO_FALLBACK.exists():
        return _REPO_FALLBACK.read_text()
    raise FileNotFoundError(
        f"could not locate {SKILL_NAME}.SKILL.md in the wheel "
        f"({_BUNDLED}) or the repo tree ({_REPO_FALLBACK})"
    )


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
