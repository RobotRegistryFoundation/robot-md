from __future__ import annotations
from unittest.mock import MagicMock
from robot_md.mcp.tools.spatial_eval.dry_run import dry_run_tool


def test_dry_run_passes_when_section_present_and_apikey_set(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    ctx = MagicMock()
    ctx.parsed = {
        "spatial-eval": {
            "spec_version": "1.0.0",
            "units": ["O1"],
            "workspace": {"play_surface_dims_m": [0.3, 0.3],
                          "judge_camera": {"device": "phone:tripod", "resolution": [1920, 1080]}},
            "reasoning_stack": {"baseline": "claude:claude-opus-4-7", "declared": "claude:claude-opus-4-7"},
        }
    }
    out = dry_run_tool(ctx)
    assert out["ok"] is True
    assert out["checks"]["spatial_eval_section"] == "present"
    assert out["checks"]["anthropic_api_key"] == "set"


def test_dry_run_fails_without_section():
    ctx = MagicMock()
    ctx.parsed = {}
    out = dry_run_tool(ctx)
    assert out["ok"] is False
    assert out["checks"]["spatial_eval_section"] == "missing"
