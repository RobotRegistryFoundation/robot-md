from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from robot_md.mcp.tools.spatial_eval.replay import replay_tool


def test_replay_recomputes_score_from_evidence(tmp_path: Path):
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "trials": [
                    {"trial_id": "o1-1", "unit": "O1", "passed": True, "reason": "ok"},
                    {"trial_id": "o1-2", "unit": "O1", "passed": False, "reason": "miss"},
                ]
            }
        )
    )
    (tmp_path / "Score.json").write_text("{}")
    out = replay_tool(MagicMock(), run_dir=tmp_path)
    assert out["ok"] is True
    assert out["score"]["tracks"]["execute"]["O1"]["passed"] == 1
    assert out["score"]["tracks"]["execute"]["O1"]["n"] == 2


def test_replay_preserves_spec_version_and_rrn_from_existing_score(tmp_path: Path):
    """I3 followup: replay should read spec_version and rrn from the existing
    Score.json instead of hardcoding defaults — preserves provenance across
    the replay/recompute cycle."""
    (tmp_path / "manifest.json").write_text(
        json.dumps({"trials": [{"trial_id": "o1-1", "unit": "O1", "passed": True}]})
    )
    (tmp_path / "Score.json").write_text(
        json.dumps(
            {
                "spec_version": "1.4.2",
                "rrn": "RRN-000000000007",
                "run_id": "original-run",
                "timestamp": "2026-04-01T00:00:00Z",
                "tracks": {"probe": {}, "execute": {}},
                "aggregate": {},
            }
        )
    )
    out = replay_tool(MagicMock(), run_dir=tmp_path)
    assert out["ok"] is True
    assert out["score"]["spec_version"] == "1.4.2"
    assert out["score"]["rrn"] == "RRN-000000000007"


def test_replay_falls_back_when_score_json_missing_fields(tmp_path: Path):
    """If Score.json is empty or missing spec_version/rrn, replay falls back
    to safe defaults rather than crashing — preserves the existing contract."""
    (tmp_path / "manifest.json").write_text(
        json.dumps({"trials": [{"trial_id": "o1-1", "unit": "O1", "passed": True}]})
    )
    (tmp_path / "Score.json").write_text("{}")
    out = replay_tool(MagicMock(), run_dir=tmp_path)
    assert out["ok"] is True
    assert out["score"]["spec_version"] == "1.0.0"
    assert out["score"]["rrn"] == "RRN-replayed"
