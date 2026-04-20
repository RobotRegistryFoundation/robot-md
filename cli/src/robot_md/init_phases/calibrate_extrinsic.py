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

    # Real sweep.
    try:
        from robot_md.calibrate_extrinsic import (
            Sample,
            plan_sweep,
            solve,
            write_extrinsic,
            CalibrationError,
        )
        from robot_md.gripper_silhouette import find_in_depth
        from robot_md.kinematics import Kinematics
        import numpy as np

        workspace = fm["physics"]["workspace"]["bounds_mm"]
        kin = Kinematics(fm)
        poses = plan_sweep(fm, workspace, n_poses=n_poses, seed=0)

        samples: list[Sample] = []
        for pose in poses:
            # Convert rad dict to step dict for the servo bus.
            step_cfg = {
                jid: kin.by_id[jid].rad_to_steps(rad)
                for jid, rad in pose.items()
                if jid in kin.by_id
            }
            # Move to pose. Read current first to hand to interpolate().
            current = bus.read_positions()
            bus.interpolate(current, step_cfg, hz=30, estop=None)

            # Capture and detect gripper in camera frame.
            frame = camera.grab_frame()
            if frame is None:
                continue
            _rgb, depth, K = frame
            tip_base = np.array(kin.fk(pose), dtype=float)

            # Initial guess for where the gripper should appear in camera frame:
            # project base-frame tip through the current (preset-default) extrinsic.
            from robot_md.extrinsic import six_vec_to_matrix
            current_ext = fm["physics"]["solver"]["cameras"][0]["extrinsic"]
            T = six_vec_to_matrix(current_ext)  # camera→base matrix
            tip_base_h = np.append(tip_base, 1.0)
            tip_cam_guess = (np.linalg.inv(T) @ tip_base_h)[:3][None, :]

            centroid, confidence = find_in_depth(depth, K, tip_cam_guess, search_radius_mm=60)
            if centroid is None or confidence < 0.3:
                continue
            samples.append(
                Sample(joints=pose, tip_cam=centroid, tip_base=tip_base, confidence=confidence)
            )

        if len(samples) < 4:
            return PhaseResult(
                phase="calibrate_extrinsic",
                status="failed",
                message=f"only {len(samples)}/{n_poses} poses produced usable observations",
                detail={
                    "reason": "gripper_not_visible",
                    "samples_kept": len(samples),
                    "samples_total": n_poses,
                },
            )

        six_vec, residual = solve(samples)
        if residual > 15.0:
            ans = (input(f"Calibration residual {residual:.1f}mm is high. Accept? [y/N] ") or "n").strip().lower()
            if not ans.startswith("y"):
                return PhaseResult(
                    phase="calibrate_extrinsic",
                    status="failed",
                    message=f"user aborted at residual {residual:.1f}mm",
                    detail={"reason": "residual_too_high", "residual_mm": residual},
                )

        write_extrinsic(
            manifest_path,
            six_vec=six_vec,
            source="gripper_silhouette_calibrated",
            residual_mm=residual,
        )
        return PhaseResult(
            phase="calibrate_extrinsic",
            status="ok",
            message=f"calibrated — residual {residual:.1f}mm",
            detail={
                "residual_mm": residual,
                "samples_kept": len(samples),
                "samples_total": n_poses,
            },
        )
    except CalibrationError as e:
        return PhaseResult(
            phase="calibrate_extrinsic",
            status="failed",
            message=str(e),
            detail={"reason": "calibration_error"},
        )
    except Exception as e:
        return PhaseResult(
            phase="calibrate_extrinsic",
            status="failed",
            message=f"unexpected error: {e}",
            detail={"reason": "unexpected", "error": str(e)},
        )
