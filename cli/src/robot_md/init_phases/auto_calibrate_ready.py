"""Init phase: compute a canonical `ready` pose from DH params, no hardware.

Skipped when `physics.solver.ik_provider` is unset (preset doesn't support
in-house IK) or when `physics.poses.ready` is already present (user
override respected). Never raises.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

import yaml

from robot_md.auto_calibrate import compute_ready_pose
from robot_md.init_phases import PhaseResult
from robot_md.parser import ParseError, parse_file


def phase_auto_calibrate_ready(*, manifest_path: Path) -> PhaseResult:
    try:
        parsed = parse_file(manifest_path)
    except ParseError as e:
        return PhaseResult(
            phase="auto_calibrate_ready",
            status="failed",
            message=f"cannot parse manifest: {e}",
            detail={"reason": "parse_error", "error": str(e)},
        )

    fm = dict(parsed.frontmatter)

    solver = (fm.get("physics") or {}).get("solver") or {}
    if not solver.get("ik_provider"):
        return PhaseResult(
            phase="auto_calibrate_ready",
            status="skipped",
            message="preset does not declare physics.solver.ik_provider",
            detail={"reason": "no_ik_provider"},
        )

    existing = ((fm.get("physics") or {}).get("poses") or {}).get("ready")
    if existing and existing.get("joints"):
        return PhaseResult(
            phase="auto_calibrate_ready",
            status="skipped",
            message="`ready` already taught; leaving untouched",
            detail={"reason": "already_set"},
        )

    steps = compute_ready_pose(fm)
    if steps is None:
        return PhaseResult(
            phase="auto_calibrate_ready",
            status="skipped",
            message="IK unreachable for default target (200, 0, 50) mm",
            detail={"reason": "ik_unreachable"},
        )

    physics = dict(fm.get("physics") or {})
    poses = dict(physics.get("poses") or {})
    poses["ready"] = {
        "description": "Auto-calibrated forward-extended pose (DH + IK).",
        "joints": {k: int(v) for k, v in steps.items()},
        "source": "solved_from_dh",
        "taught_at": _dt.date.today().isoformat(),
    }
    physics["poses"] = poses
    fm["physics"] = physics

    manifest_path.write_text("---\n" + yaml.safe_dump(fm, sort_keys=False) + "---\n" + parsed.body)
    return PhaseResult(
        phase="auto_calibrate_ready",
        status="ok",
        message=f"solved `ready` ({len(steps)} joints) from DH params",
        detail={"pose_name": "ready", "joints": steps},
    )
