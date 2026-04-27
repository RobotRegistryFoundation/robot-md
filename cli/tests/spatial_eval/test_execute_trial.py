from __future__ import annotations

from pathlib import Path

import numpy as np

from robot_md.spatial_eval.execute.trial import FakeJudgeCamera, FakeRobot, run_trial


def _bgr(color):
    img = np.zeros((240, 320, 3), dtype=np.uint8)
    img[:, :] = color
    return img


def test_o1_pass_when_target_retrieved_and_occluder_steady(tmp_path: Path):
    robot = FakeRobot(actions=["pick_target_color:red_cube"])
    cam = FakeJudgeCamera(
        frames=[
            _bgr((0, 0, 255)),  # t0: red present
            _bgr((0, 200, 0)),  # t1: green occluder (red hidden)
            _bgr((0, 0, 255)),  # t2: red retrieved (post-action)
        ]
    )
    outcome = run_trial(unit="O1", trial_id="o1-1", robot=robot, judge_camera=cam, run_dir=tmp_path)
    assert outcome["passed"] is True


def test_o1_fail_when_target_not_retrieved(tmp_path: Path):
    robot = FakeRobot(actions=["miss"])
    cam = FakeJudgeCamera(
        frames=[
            _bgr((0, 0, 255)),
            _bgr((0, 200, 0)),
            _bgr((0, 200, 0)),  # never reappears
        ]
    )
    outcome = run_trial(unit="O1", trial_id="o1-2", robot=robot, judge_camera=cam, run_dir=tmp_path)
    assert outcome["passed"] is False
