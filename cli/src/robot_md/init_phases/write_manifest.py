"""Phase: write ROBOT.md from preset + hardware scan."""

from __future__ import annotations

from pathlib import Path

from robot_md.init import (
    load_presets,
    merge_preset_into_draft,
    pick_best,
    render_draft,
)
from robot_md.init_phases import PhaseResult


def phase_write_manifest(
    *,
    out_path: Path,
    robot_name: str | None,
    preset_name: str | None,
    scan,
    force: bool = False,
) -> PhaseResult:
    """Write a validated ROBOT.md draft. Returns PhaseResult; never raises
    for recoverable errors. Fatal I/O errors (disk full) may still raise.
    """
    if out_path.exists() and not force:
        return PhaseResult(
            phase="write_manifest",
            status="failed",
            message=f"{out_path} already exists (pass --force to overwrite)",
            detail={"reason": "exists", "path": str(out_path)},
        )

    presets = load_presets()
    if not presets:
        return PhaseResult(
            phase="write_manifest",
            status="failed",
            message="no presets found in preset directory",
            detail={"reason": "no_presets"},
        )

    if preset_name:
        sel = next(
            (p for p in presets if p.name == preset_name or p.display_name == preset_name),
            None,
        )
        if sel is None:
            names = [p.display_name for p in presets]
            return PhaseResult(
                phase="write_manifest",
                status="failed",
                message=f"preset {preset_name!r} not found. Available: {names}",
                detail={"reason": "unknown_preset", "requested": preset_name},
            )
        from robot_md.init import MatchResult

        chosen = MatchResult(preset=sel, score=100, reasons=["explicit --preset"])
    else:
        chosen = pick_best(presets, scan)
        if chosen is None:
            return PhaseResult(
                phase="write_manifest",
                status="failed",
                message="preset list empty after pick_best",
                detail={"reason": "pick_best_empty"},
            )

    import socket

    name = robot_name or f"robot-{socket.gethostname()}"
    fm = merge_preset_into_draft(chosen.preset, name, scan)
    body_hints = chosen.preset.data.get("body_hints", {}) or {}
    text = render_draft(fm, body_hints)
    out_path.write_text(text)

    return PhaseResult(
        phase="write_manifest",
        status="ok",
        message=f"wrote {out_path.name} (preset {chosen.preset.display_name})",
        detail={
            "path": str(out_path),
            "preset": chosen.preset.display_name,
            "score": chosen.score,
            "reasons": chosen.reasons,
            "robot_name": name,
        },
    )
