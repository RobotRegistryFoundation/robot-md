"""SP6 Phase 1.5 — `robot-md spatial-eval submit-to-rrf <score.json>` CLI.

Uses Typer's CliRunner against the spatial_eval sub-app. Mocks
urllib.request.urlopen the same way as test_rrf_submit_score.py.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from robot_md.__main__ import app
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
    apikey = tmp_path / ".robot-md" / "keys" / "RRN-000000000002.apikey"
    apikey.parent.mkdir(parents=True, exist_ok=True)
    apikey.write_text("bob-apikey")
    return tmp_path


def _signed_score_path(dest_dir: Path) -> Path:
    s = ScoreJSON(
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
    p = dest_dir / "Score.json"
    p.write_text(s.to_json())
    return p


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


def test_submit_to_rrf_cli_happy_path(home, tmp_path):
    score_path = _signed_score_path(tmp_path)

    def fake_urlopen(req, timeout=None):
        return _mock_response(202, {"submission_id": "sub_x", "status": "pending"})

    runner = CliRunner()
    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = runner.invoke(app, ["spatial-eval", "submit-to-rrf", str(score_path)])

    assert result.exit_code == 0, result.output
    out = json.loads(result.stdout)
    assert out["submission_id"] == "sub_x"
    assert out["status"] == "pending"


def test_submit_to_rrf_cli_unsigned_score_exits_2(home, tmp_path):
    s = ScoreJSON(
        spec_version="1.0.0",
        rrn="RRN-000000000002",
        run_id="run-1",
        timestamp="t",
        tracks_probe=ProbeTrack(baseline_claude={}, robot_declared={}, delta_per_unit={}),
        tracks_execute={},
        aggregate=Aggregate(0.0, 0.0, 0.0),
        rcan_signature=None,
    )
    p = tmp_path / "Score.json"
    p.write_text(s.to_json())

    runner = CliRunner()
    result = runner.invoke(app, ["spatial-eval", "submit-to-rrf", str(p)])
    assert result.exit_code == 2
    assert "no rcan_signature" in result.output


def test_submit_to_rrf_cli_missing_file_exits_with_typer_error(home, tmp_path):
    runner = CliRunner()
    result = runner.invoke(app, ["spatial-eval", "submit-to-rrf", str(tmp_path / "nope.json")])
    # Typer's exists=True triggers a usage error (exit code 2).
    assert result.exit_code != 0
