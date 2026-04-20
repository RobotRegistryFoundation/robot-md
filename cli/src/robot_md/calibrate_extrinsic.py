"""Camera-to-base extrinsic calibration via gripper-silhouette sweep.

Replaces the v0.6.x ArUco hand-eye path (removed in v0.7). No printed
marker; the gripper tip is the fiducial, positioned by FK.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

import numpy as np

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
        risk = kin.analyze_envelope(cfg, duration_ms=1000)
        if risk.level != "ok":
            continue
        poses.append(cfg)
    if len(poses) < n_poses:
        raise CalibrationError(
            f"could only generate {len(poses)}/{n_poses} safe poses inside the workspace; "
            f"widen workspace bounds or reduce n_poses"
        )
    return poses
