from __future__ import annotations
from unittest.mock import MagicMock
from robot_md.mcp.tools.spatial_eval.submit_to_rrf import submit_to_rrf_tool


def test_submit_returns_pending_phase_1():
    out = submit_to_rrf_tool(MagicMock(), run_dir="/tmp/run-x")
    assert out["ok"] is True
    assert out["status"] == "pending_phase_1"
