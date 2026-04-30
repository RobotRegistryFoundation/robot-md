"""SP6 — MCP tool wrapper for spatial_eval_submit_to_rrf.

Thin wrapper over `robot_md.spatial_eval.rrf.submit_score`: reads
Score.json from run_dir, surfaces missing-file and missing-signature
errors as `{"ok": False, "error": ...}`, otherwise returns the §27
response wrapped with `ok=True`.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from robot_md.mcp.tools.spatial_eval.submit_to_rrf import submit_to_rrf_tool
from robot_md.spatial_eval.score import (
    Aggregate,
    PerUnitExecuteScore,
    PerUnitProbeScore,
    ProbeTrack,
    ScoreJSON,
)


@pytest.fixture
def home(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    apikey_path = tmp_path / ".robot-md" / "keys" / "RRN-000000000002.apikey"
    apikey_path.parent.mkdir(parents=True, exist_ok=True)
    apikey_path.write_text("bob-apikey")
    return tmp_path


def _signed_score_on_disk(run_dir: Path) -> Path:
    score = ScoreJSON(
        spec_version="1.0.0",
        rrn="RRN-000000000002",
        run_id="run-1",
        timestamp="2026-04-30T18:00:00Z",
        tracks_probe=ProbeTrack(
            baseline_claude={"O1": PerUnitProbeScore(score=0.87, n=30, passed=26)},
            robot_declared={"O1": PerUnitProbeScore(score=0.84, n=30, passed=25)},
            delta_per_unit={"O1": -0.03},
        ),
        tracks_execute={"O1": PerUnitExecuteScore(passed=7, n=10, evidence_sha256="abc")},
        aggregate=Aggregate(probe_baseline=0.87, probe_declared=0.84, execute=0.7),
        rcan_signature="rcan-sig",
        evidence_root="sha256:e1",
    )
    score_path = run_dir / "Score.json"
    score_path.write_text(score.to_json())
    return score_path


def _mock_response(status: int, body: dict) -> object:
    class _Resp:
        def __init__(self):
            self.status = status
            self._fp = io.BytesIO(json.dumps(body).encode())

        def read(self):
            return self._fp.read()

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    return _Resp()


def test_submit_to_rrf_missing_score_json_returns_error(tmp_path):
    out = submit_to_rrf_tool(MagicMock(), run_dir=str(tmp_path))
    assert out["ok"] is False
    assert "Score.json not found" in out["error"]


def test_submit_to_rrf_unsigned_score_returns_error(tmp_path):
    score = ScoreJSON(
        spec_version="1.0.0",
        rrn="RRN-000000000002",
        run_id="run-1",
        timestamp="2026-04-30T18:00:00Z",
        tracks_probe=ProbeTrack(
            baseline_claude={}, robot_declared={}, delta_per_unit={}
        ),
        tracks_execute={},
        aggregate=Aggregate(probe_baseline=0.0, probe_declared=0.0, execute=0.0),
        rcan_signature=None,
    )
    (tmp_path / "Score.json").write_text(score.to_json())
    out = submit_to_rrf_tool(MagicMock(), run_dir=str(tmp_path))
    assert out["ok"] is False
    assert "rcan_signature" in out["error"]


def test_submit_to_rrf_happy_path_returns_pending(home, tmp_path):
    run_dir = tmp_path / "run-x"
    run_dir.mkdir()
    _signed_score_on_disk(run_dir)

    def fake_urlopen(req, timeout=None):
        return _mock_response(202, {"submission_id": "sub_x", "status": "pending"})

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        out = submit_to_rrf_tool(MagicMock(), run_dir=str(run_dir))

    assert out["ok"] is True
    assert out["status"] == "pending"
    assert out["submission_id"] == "sub_x"
