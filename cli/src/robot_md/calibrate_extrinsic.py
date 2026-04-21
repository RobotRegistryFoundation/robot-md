"""Camera-to-base extrinsic calibration via gripper-silhouette sweep.

Replaces the v0.6.x ArUco hand-eye path (removed in v0.7). No printed
marker; the gripper tip is the fiducial, positioned by FK.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any

import numpy as np

from robot_md.gripper_silhouette import find_via_motion_delta
from robot_md.kinematics import Kinematics


@dataclass
class Sample:
    joints: dict[str, float]
    tip_cam: np.ndarray  # (3,) camera-frame mm
    tip_base: np.ndarray  # (3,) base-frame mm
    confidence: float


@dataclass
class CalibrationResult:
    extrinsic_6vec: list[float]
    residual_mm: float
    samples_kept: int
    samples_total: int


class CalibrationError(Exception):
    """Sweep or solve failed unrecoverably."""


def plan_sweep(
    frontmatter: dict[str, Any],
    workspace_bounds: dict[str, list[float]],
    *,
    n_poses: int = 6,
    seed: int = 0,
) -> list[dict[str, float]]:
    """Generate n_poses joint configurations whose FK tip lies inside the
    workspace cuboid AND whose envelope is safe (analyze_envelope == ok).

    Strategy: sample a deterministic Halton-like sequence of target tip
    XYZ inside the workspace; ik_reach each; reject on envelope risk.
    Abort with CalibrationError if we can't find n_poses in 200 tries.
    """
    kin = Kinematics(frontmatter)
    rng = random.Random(seed)
    xs = workspace_bounds["x"]
    ys = workspace_bounds["y"]
    zs = workspace_bounds["z"]

    poses: list[dict[str, float]] = []
    tries = 0
    while len(poses) < n_poses and tries < 200:
        tries += 1
        # Bias z toward the middle of the envelope — too-low is near the
        # tabletop (risk of collision), too-high is near wrist_flex limit.
        x = rng.uniform(xs[0] + 20, xs[1] - 20)
        y = rng.uniform(ys[0] + 20, ys[1] - 20)
        z = rng.uniform(zs[0] + 30, min(zs[1] - 10, zs[0] + 150))
        try:
            cfg = kin.ik_reach((x, y, z))
        except Exception:
            continue
        # Sweep poses are transient (held only long enough for one frame
        # capture, << 500ms), so use duration_ms=200 — far below
        # TRANSIENT_MS. Using 1000ms here would reject IK-reachable poses
        # on real ±90° limits that are totally safe when held briefly.
        risk = kin.analyze_envelope(cfg, duration_ms=200)
        if risk.level != "ok":
            continue
        poses.append(cfg)
    if len(poses) < n_poses:
        raise CalibrationError(
            f"could only generate {len(poses)}/{n_poses} safe poses inside the workspace; "
            f"widen workspace bounds or reduce n_poses"
        )
    return poses


def capture_via_wrist_wiggle(
    bus: Any,
    camera: Any,
    kin: Kinematics,
    pose: dict[str, float],
    *,
    wiggle_rad: float = 0.15,
    settle_s: float = 0.4,
) -> tuple[dict[str, float] | None, np.ndarray | None, float]:
    """Capture a gripper observation by wiggling ONLY wrist_flex between
    two depth frames.

    Moves the arm to ``pose``, captures ``depth_A``, shifts wrist_flex by
    ±``wiggle_rad`` (sign chosen to stay within joint limits), captures
    ``depth_B``, and returns the motion-delta centroid.

    Because only wrist_flex moved between frames, the centroid is the
    gripper's silhouette — not a forearm-dominated average, which is the
    failure mode of pose-to-pose motion delta used in v0.7.3.

    Returns ``(wiggled_pose, centroid_cam, confidence)``. On failure
    (joint missing, both directions outside limits, camera grab failed,
    motion cluster too small) returns ``(None, None, 0.0)``.
    """
    wrist = kin.by_id.get("wrist_flex")
    if wrist is None:
        return None, None, 0.0

    base_angle = pose.get("wrist_flex", 0.0)
    lo, hi = wrist.limits_rad
    if base_angle + wiggle_rad <= hi:
        delta = wiggle_rad
    elif base_angle - wiggle_rad >= lo:
        delta = -wiggle_rad
    else:
        return None, None, 0.0

    wiggled_pose = dict(pose)
    wiggled_pose["wrist_flex"] = base_angle + delta

    pose_steps = {
        jid: kin.by_id[jid].rad_to_steps(rad) for jid, rad in pose.items() if jid in kin.by_id
    }
    wiggled_steps = dict(pose_steps)
    wiggled_steps["wrist_flex"] = kin.by_id["wrist_flex"].rad_to_steps(wiggled_pose["wrist_flex"])

    start_steps = bus.read_positions()
    bus.interpolate(start_steps, pose_steps, hz=30, estop=None)
    time.sleep(settle_s)
    frame_a = camera.grab_frame()
    if frame_a is None:
        return None, None, 0.0
    _rgb_a, depth_a, K = frame_a

    bus.interpolate(pose_steps, wiggled_steps, hz=30, estop=None)
    time.sleep(settle_s)
    frame_b = camera.grab_frame()
    if frame_b is None:
        return None, None, 0.0
    _rgb_b, depth_b, _K_b = frame_b

    centroid, confidence = find_via_motion_delta(depth_a, depth_b, K)
    if centroid is None:
        return None, None, 0.0
    return wiggled_pose, centroid, confidence


def solve(samples: list[Sample]) -> tuple[list[float], float]:
    """Rigid-body (Kabsch) registration: find T_cam_to_base so that for each
    sample, T @ tip_cam ≈ tip_base. Returns (six_vec, mean_residual_mm).
    """
    from robot_md.extrinsic import matrix_to_six_vec

    if len(samples) < 3:
        raise CalibrationError(f"need at least 3 samples, got {len(samples)}")

    P = np.array([s.tip_cam for s in samples], dtype=float)  # camera frame
    Q = np.array([s.tip_base for s in samples], dtype=float)  # base frame

    cP = P.mean(axis=0)
    cQ = Q.mean(axis=0)
    Pc = P - cP
    Qc = Q - cQ
    H = Pc.T @ Qc
    try:
        U, S, Vt = np.linalg.svd(H)
    except np.linalg.LinAlgError as e:
        raise CalibrationError(f"SVD failed: {e}") from e

    if float(S.min()) < 1e-6:
        raise CalibrationError(
            "samples are collinear or coplanar; widen sweep across all workspace axes"
        )

    D = np.diag([1.0, 1.0, float(np.linalg.det(Vt.T @ U.T))])
    R = Vt.T @ D @ U.T
    t = cQ - R @ cP

    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = t

    six = matrix_to_six_vec(T)

    residuals = np.linalg.norm((R @ P.T).T + t - Q, axis=1)
    mean_residual = float(residuals.mean())
    return list(six), mean_residual


def write_extrinsic(
    manifest_path,
    *,
    six_vec: list[float],
    source: str = "gripper_silhouette_calibrated",
    residual_mm: float | None = None,
) -> None:
    """Write extrinsic + provenance into manifest's physics.solver.cameras[0].
    Preserves comments via ruamel.yaml.
    """
    import io
    from pathlib import Path

    from ruamel.yaml import YAML

    p = Path(manifest_path)
    text = p.read_text()
    end = text.find("\n---", 3)
    if end < 0:
        raise CalibrationError(f"could not locate frontmatter end in {p}")
    fm_text = text[3:end].lstrip("\n")
    body_text = text[end + 4 :]

    y = YAML()
    y.preserve_quotes = True
    y.indent(mapping=2, sequence=4, offset=2)
    data = y.load(fm_text)
    solver = data.setdefault("physics", {}).setdefault("solver", {})
    cams = solver.setdefault("cameras", [{}])
    if not cams:
        cams.append({})
    cams[0]["extrinsic"] = [float(v) for v in six_vec]
    cams[0]["extrinsic_source"] = source
    if residual_mm is not None:
        cams[0]["extrinsic_residual_mm"] = round(float(residual_mm), 3)

    buf = io.StringIO()
    y.dump(data, buf)
    p.write_text("---\n" + buf.getvalue().rstrip("\n") + "\n---" + body_text)
