"""Phase: install the using-robot-md skill into the operator's skills dir."""

from __future__ import annotations

from pathlib import Path

from robot_md.init_phases import PhaseResult
from robot_md.skill import install as skill_install


def phase_install_skill(
    *,
    dest_root: Path | None = None,
    force: bool = True,
) -> PhaseResult:
    """Install the using-robot-md skill. Idempotent with force=True (default)."""
    try:
        path = skill_install(dest_root=dest_root, force=force)
    except FileExistsError as e:
        return PhaseResult(
            phase="install_skill",
            status="ok",
            message=f"skill already installed — {e}",
            detail={"already_installed": True},
        )
    except FileNotFoundError as e:
        return PhaseResult(
            phase="install_skill",
            status="failed",
            message=f"bundled skill content missing: {e}",
            detail={"reason": "skill_content_missing", "error": str(e)},
        )
    except PermissionError as e:
        return PhaseResult(
            phase="install_skill",
            status="failed",
            message=f"permission denied installing skill: {e}",
            detail={"reason": "permission_error", "error": str(e)},
        )

    return PhaseResult(
        phase="install_skill",
        status="ok",
        message=f"installed at {path}",
        detail={"path": str(path), "already_installed": False},
    )
