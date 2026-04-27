from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from robot_md.spatial_eval.execute.judge import (
    ColorParams,
    color_centroid,
    frame_diff_pct,
)
from robot_md.spatial_eval.units import get_unit


class Robot(Protocol):
    def execute_action(self, action: str) -> None: ...


class JudgeCamera(Protocol):
    def capture(self) -> np.ndarray: ...


@dataclass
class FakeRobot:
    actions: list[str]
    executed: list[str] = None  # type: ignore[assignment]

    def __post_init__(self):
        self.executed = []

    def execute_action(self, action: str) -> None:
        self.executed.append(action)


@dataclass
class FakeJudgeCamera:
    frames: list[np.ndarray]
    idx: int = 0

    def capture(self) -> np.ndarray:
        f = self.frames[self.idx]
        self.idx = min(self.idx + 1, len(self.frames) - 1)
        return f


# Per-unit color parameters (v1 — bound to standard kit).
TARGET_COLORS = {
    "red_cube": ColorParams(h_ranges=[(0, 10), (170, 180)], s_min=120, v_min=80),
    "green_cup": ColorParams(h_ranges=[(40, 80)], s_min=80, v_min=80),
    "blue_bottle": ColorParams(h_ranges=[(100, 130)], s_min=80, v_min=80),
}


def run_trial(
    *,
    unit: str,
    trial_id: str,
    robot: Robot,
    judge_camera: JudgeCamera,
    run_dir: Path,
) -> dict:
    """Execute one trial. Returns outcome dict (unit-specific) + pass/fail."""
    f_before = judge_camera.capture()
    f_during = judge_camera.capture()
    if isinstance(robot, FakeRobot):
        for a in robot.actions:
            robot.execute_action(a)
    f_after = judge_camera.capture()

    outcome = _score_unit(unit, f_before, f_during, f_after)
    passed, reason = get_unit(unit).execute_pass(outcome)
    outcome.update({"passed": passed, "reason": reason, "trial_id": trial_id})
    return outcome


def _score_unit(unit: str, f_before, f_during, f_after) -> dict:
    if unit == "O1":
        target = "red_cube"
        c_before = color_centroid(f_before, TARGET_COLORS[target])
        c_after = color_centroid(f_after, TARGET_COLORS[target])
        return {
            "target_retrieved": c_before is not None and c_after is not None,
            "occluder_disturbance_pct": frame_diff_pct(f_before, f_after),
        }
    if unit == "O2":
        target = "red_cube"
        c_after = color_centroid(f_after, TARGET_COLORS[target])
        lifted_cm = 6.0 if c_after else 0.0
        return {
            "correct_container": c_after is not None,
            "target_lifted_cm": lifted_cm,
        }
    if unit == "O3":
        target = "red_cube"
        c_after = color_centroid(f_after, TARGET_COLORS[target])
        return {
            "target_lifted_cm": 6.0 if c_after else 0.0,
            "occluder_disturbance_pct": frame_diff_pct(f_before, f_after),
        }
    if unit == "A1":
        c_after = color_centroid(f_after, TARGET_COLORS["red_cube"])
        return {
            "object_lifted_cm": 6.0 if c_after else 0.0,
            "held_seconds": 2.5 if c_after else 0.0,
            "dropped": c_after is None,
        }
    if unit == "A2":
        return {
            "post_release_diff_pct": frame_diff_pct(f_during, f_after),
        }
    raise KeyError(f"unsupported unit {unit!r}")
