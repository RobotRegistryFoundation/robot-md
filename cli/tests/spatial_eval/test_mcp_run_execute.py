from __future__ import annotations
from pathlib import Path
from unittest.mock import MagicMock
import numpy as np
from robot_md.mcp.tools.spatial_eval.run_execute import run_execute_tool
from robot_md.spatial_eval.execute.trial import FakeRobot, FakeJudgeCamera


def _bgr(c):
    img = np.zeros((240, 320, 3), np.uint8)
    img[:, :] = c
    return img


def test_run_execute_emits_score_and_evidence(tmp_path: Path):
    ctx = MagicMock()
    ctx.parsed = {
        "id": "bob",
        "spatial-eval": {
            "spec_version": "1.0.0", "units": ["O1"],
            "workspace": {"play_surface_dims_m": [0.3, 0.3],
                          "judge_camera": {"device": "phone:tripod", "resolution": [1920, 1080]}},
            "reasoning_stack": {"baseline": "claude:c", "declared": "claude:c"},
        },
    }
    robot = FakeRobot(actions=["pick_target_color:red_cube"])
    cam = FakeJudgeCamera(frames=[_bgr((0, 0, 255))] * 3)
    out = run_execute_tool(
        ctx, units=["O1"], trials_per_unit=2, run_dir=tmp_path,
        _robot=robot, _judge_camera=cam,
    )
    assert out["ok"] is True
    assert (tmp_path / "Score.json").is_file()
    assert out["score"]["tracks"]["execute"]["O1"]["n"] == 2
