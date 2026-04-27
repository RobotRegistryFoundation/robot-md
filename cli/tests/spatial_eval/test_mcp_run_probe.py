from __future__ import annotations
from unittest.mock import MagicMock
from robot_md.mcp.tools.spatial_eval.run_probe import run_probe_tool
from robot_md.spatial_eval.probe.stacks import FakeStack


def _ctx_with_section():
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
    return ctx


def test_run_probe_returns_score():
    ctx = _ctx_with_section()
    # Canned answers chosen to match the public probe truths so at least one
    # passes (probe-001 truth is still_present=True at [0, 0.05, 0]).
    fake = FakeStack({
        "o1-public-001": {"still_present": True, "position": [0.0, 0.05, 0.0]},
        "o1-public-002": {"still_present": True, "position": [0.10, 0.0, 0.0]},
        "o1-public-003": {"still_present": False, "position": [-0.05, 0.08, 0.0]},
    })
    out = run_probe_tool(
        ctx, units=["O1"], baseline_only=True,
        _stacks={"baseline": fake, "declared": fake},
    )
    assert out["ok"] is True
    assert "score" in out
    assert out["score"]["tracks"]["probe"]["baseline_claude"]["O1"]["passed"] >= 1
