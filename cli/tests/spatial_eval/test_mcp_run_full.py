from __future__ import annotations
from pathlib import Path
from unittest.mock import MagicMock
import numpy as np
from robot_md.mcp.tools.spatial_eval.run_full import run_full_tool
from robot_md.spatial_eval.probe.stacks import FakeStack
from robot_md.spatial_eval.execute.trial import FakeRobot, FakeJudgeCamera


def _bgr(c):
    img = np.zeros((240, 320, 3), np.uint8)
    img[:, :] = c
    return img


def test_run_full_merges_both_tracks(tmp_path: Path):
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
    fake = FakeStack({
        "o1-public-001": {"still_present": True, "position": [0.0, 0.05, 0.0]},
        "o1-public-002": {"still_present": True, "position": [0.10, 0.0, 0.0]},
        "o1-public-003": {"still_present": False, "position": [-0.05, 0.08, 0.0]},
    })
    robot = FakeRobot(actions=["pick"])
    cam = FakeJudgeCamera(frames=[_bgr((0, 0, 255))] * 3)
    out = run_full_tool(
        ctx, units=["O1"], trials_per_unit=2, run_dir=tmp_path,
        _stacks={"baseline": fake, "declared": fake},
        _robot=robot, _judge_camera=cam,
    )
    assert out["ok"] is True
    assert "baseline_claude" in out["score"]["tracks"]["probe"]
    assert out["score"]["tracks"]["execute"]["O1"]["n"] == 2
