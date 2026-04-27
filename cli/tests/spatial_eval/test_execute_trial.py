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


# ---- O2 (container reasoning) -------------------------------------------


def test_o2_pass_when_correct_container_and_target_lifted(tmp_path: Path):
    robot = FakeRobot(actions=["lift_container", "retrieve_target"])
    cam = FakeJudgeCamera(
        frames=[
            _bgr((0, 200, 0)),  # green container hides red
            _bgr((0, 200, 0)),
            _bgr((0, 0, 255)),  # red retrieved → correct_container=True, lifted=6cm
        ]
    )
    outcome = run_trial(unit="O2", trial_id="o2-1", robot=robot, judge_camera=cam, run_dir=tmp_path)
    assert outcome["passed"] is True
    assert outcome["correct_container"] is True
    assert outcome["target_lifted_cm"] >= 5.0


def test_o2_fail_when_wrong_container(tmp_path: Path):
    robot = FakeRobot(actions=["lift_wrong_container"])
    cam = FakeJudgeCamera(
        frames=[
            _bgr((0, 200, 0)),
            _bgr((0, 200, 0)),
            _bgr((0, 200, 0)),  # red never appears → correct_container=False
        ]
    )
    outcome = run_trial(unit="O2", trial_id="o2-2", robot=robot, judge_camera=cam, run_dir=tmp_path)
    assert outcome["passed"] is False
    assert outcome["correct_container"] is False


# ---- O3 (partial-view shape) --------------------------------------------


def test_o3_pass_when_lifted_with_low_occluder_disturbance(tmp_path: Path):
    robot = FakeRobot(actions=["grasp_full_extent"])
    same = _bgr((0, 0, 255))  # identical frames → 0% disturbance, target visible
    cam = FakeJudgeCamera(frames=[same.copy(), same.copy(), same.copy()])
    outcome = run_trial(unit="O3", trial_id="o3-1", robot=robot, judge_camera=cam, run_dir=tmp_path)
    assert outcome["passed"] is True
    assert outcome["target_lifted_cm"] >= 5.0
    assert outcome["occluder_disturbance_pct"] <= 5.0


def test_o3_fail_when_target_not_lifted(tmp_path: Path):
    robot = FakeRobot(actions=["miss"])
    cam = FakeJudgeCamera(
        frames=[
            _bgr((0, 200, 0)),
            _bgr((0, 200, 0)),
            _bgr((0, 200, 0)),  # red never visible → lifted=0
        ]
    )
    outcome = run_trial(unit="O3", trial_id="o3-2", robot=robot, judge_camera=cam, run_dir=tmp_path)
    assert outcome["passed"] is False


# ---- A1 (graspable region) ----------------------------------------------


def test_a1_pass_when_object_lifted_and_held(tmp_path: Path):
    robot = FakeRobot(actions=["pick_with_grasp"])
    cam = FakeJudgeCamera(
        frames=[
            _bgr((0, 0, 255)),  # red object on table
            _bgr((0, 0, 255)),
            _bgr((0, 0, 255)),  # still held → not dropped, lifted=6, held=2.5
        ]
    )
    outcome = run_trial(unit="A1", trial_id="a1-1", robot=robot, judge_camera=cam, run_dir=tmp_path)
    assert outcome["passed"] is True
    assert outcome["dropped"] is False
    assert outcome["held_seconds"] >= 2.0


def test_a1_fail_when_object_dropped(tmp_path: Path):
    robot = FakeRobot(actions=["bad_grasp"])
    cam = FakeJudgeCamera(
        frames=[
            _bgr((0, 0, 255)),
            _bgr((0, 0, 255)),
            _bgr((0, 200, 0)),  # red gone → dropped=True
        ]
    )
    outcome = run_trial(unit="A1", trial_id="a1-2", robot=robot, judge_camera=cam, run_dir=tmp_path)
    assert outcome["passed"] is False
    assert outcome["dropped"] is True


# ---- A2 (stability-aware placement) -------------------------------------


def test_a2_pass_when_object_stays_put_after_release(tmp_path: Path):
    robot = FakeRobot(actions=["place_stable"])
    same = _bgr((0, 0, 255))
    cam = FakeJudgeCamera(frames=[same.copy(), same.copy(), same.copy()])
    outcome = run_trial(unit="A2", trial_id="a2-1", robot=robot, judge_camera=cam, run_dir=tmp_path)
    assert outcome["passed"] is True
    assert outcome["post_release_diff_pct"] <= 2.0


def test_a2_fail_when_object_topples(tmp_path: Path):
    robot = FakeRobot(actions=["place_unstable"])
    cam = FakeJudgeCamera(
        frames=[
            _bgr((0, 0, 255)),  # before
            _bgr((0, 0, 255)),  # during release (object placed)
            _bgr((0, 200, 0)),  # after — large frame diff (object toppled / scene shifted)
        ]
    )
    outcome = run_trial(unit="A2", trial_id="a2-2", robot=robot, judge_camera=cam, run_dir=tmp_path)
    assert outcome["passed"] is False
    assert outcome["post_release_diff_pct"] > 2.0
