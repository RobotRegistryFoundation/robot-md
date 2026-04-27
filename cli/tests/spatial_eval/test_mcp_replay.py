from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from robot_md.mcp.tools.spatial_eval.replay import replay_tool


def test_replay_recomputes_score_from_evidence(tmp_path: Path):
    (tmp_path / "manifest.json").write_text(json.dumps({"trials": [
        {"trial_id": "o1-1", "unit": "O1", "passed": True, "reason": "ok"},
        {"trial_id": "o1-2", "unit": "O1", "passed": False, "reason": "miss"},
    ]}))
    (tmp_path / "Score.json").write_text("{}")
    out = replay_tool(MagicMock(), run_dir=tmp_path)
    assert out["ok"] is True
    assert out["score"]["tracks"]["execute"]["O1"]["passed"] == 1
    assert out["score"]["tracks"]["execute"]["O1"]["n"] == 2
