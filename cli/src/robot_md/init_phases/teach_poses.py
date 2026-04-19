"""Init phase: offer to teach the 'ready' pose if we have a TTY.

Skipped on non-interactive runs — explicit `robot-md pose teach` is the
scripted path. Uses the same servo-bus-reading machinery as the CLI verb.
"""

from __future__ import annotations

from pathlib import Path

from robot_md.init_phases import PhaseResult


def _open_feetech_bus(manifest_path: Path):  # test-overridable seam
    from robot_md.mcp.context import load_context

    ctx = load_context(manifest_path)
    bus = getattr(ctx.backend, "_servo_bus", None)
    if bus is None:
        raise RuntimeError("no feetech servo bus for manifest")
    return bus


def _prompt_confirm(msg: str) -> bool:  # test-overridable seam
    try:
        return input(f"{msg} [y/N] ").strip().lower().startswith("y")
    except EOFError:
        return False


def phase_teach_poses(*, manifest_path: Path, interactive: bool) -> PhaseResult:
    if not interactive:
        return PhaseResult(
            phase="teach_poses",
            status="skipped",
            message="non-interactive; run `robot-md pose teach ready` separately",
            detail={"reason": "non_interactive"},
        )
    if not _prompt_confirm(
        "Teach the 'ready' pose now? "
        "(pose the arm by hand — gripper over workspace — before confirming)"
    ):
        return PhaseResult(
            phase="teach_poses",
            status="skipped",
            message="operator declined",
            detail={"reason": "declined"},
        )
    try:
        bus = _open_feetech_bus(manifest_path)
    except Exception as e:
        return PhaseResult(
            phase="teach_poses",
            status="failed",
            message=f"bus unavailable: {e}",
            detail={"reason": "bus_error", "error": str(e)},
        )
    from robot_md.poses import teach_pose

    joints = teach_pose(bus, manifest_path, name="ready")
    return PhaseResult(
        phase="teach_poses",
        status="ok",
        message=f"taught 'ready' ({len(joints)} joints)",
        detail={"pose_names": ["ready"], "joints": joints},
    )
