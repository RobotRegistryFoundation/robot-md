"""Init phase: camera-to-arm extrinsic calibration via gripper silhouette.

Skips cleanly in any of: non-interactive, no camera, no actuatable bus,
already-calibrated manifest, user declines the TTY prompt.

Task 10 ships only the skip-path logic; the full sweep/solve/write is
wired in Task 11 (which also removes the legacy hand_eye.py ArUco path).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from robot_md.init_phases import PhaseResult
from robot_md.parser import parse_file


def phase_calibrate_extrinsic(
    manifest_path: Path,
    *,
    bus: Any | None,
    camera: Any | None,
    interactive: bool = True,
    n_poses: int = 6,
) -> PhaseResult:
    """Opt-in init phase; writes `extrinsic_source: gripper_silhouette_calibrated`
    plus the computed 6-vec back into the manifest on success.
    """
    if not interactive:
        return PhaseResult(
            phase="calibrate_extrinsic",
            status="skipped",
            message="non-interactive run — extrinsic left as preset_default",
            detail={"reason": "non_interactive"},
        )
    if camera is None:
        return PhaseResult(
            phase="calibrate_extrinsic",
            status="skipped",
            message="no camera detected",
            detail={"reason": "no_camera"},
        )
    if bus is None:
        return PhaseResult(
            phase="calibrate_extrinsic",
            status="skipped",
            message="no actuatable servo bus",
            detail={"reason": "no_actuatable_bus"},
        )

    try:
        fm = parse_file(manifest_path).frontmatter
        source = (
            fm.get("physics", {})
            .get("solver", {})
            .get("cameras", [{}])[0]
            .get("extrinsic_source", "preset_default")
        )
    except Exception as e:
        return PhaseResult(
            phase="calibrate_extrinsic",
            status="failed",
            message=f"could not parse manifest: {e}",
            detail={"reason": "parse_error"},
        )

    if source != "preset_default":
        return PhaseResult(
            phase="calibrate_extrinsic",
            status="skipped",
            message=f"extrinsic source is '{source}', not preset_default",
            detail={"reason": "already_calibrated", "source": source},
        )

    answer = (input("Calibrate camera-to-arm alignment now? The arm will move through "
                    f"{n_poses} poses. [Y/n] ") or "y").strip().lower()
    if answer.startswith("n"):
        return PhaseResult(
            phase="calibrate_extrinsic",
            status="skipped",
            message="user declined",
            detail={"reason": "declined"},
        )

    # Full sweep implemented in Task 11 — for now, placeholder that tests
    # exercise the skip paths only. Task 11 swaps this branch for the real run.
    return PhaseResult(
        phase="calibrate_extrinsic",
        status="skipped",
        message="full sweep not yet wired (Task 11)",
        detail={"reason": "not_implemented"},
    )
