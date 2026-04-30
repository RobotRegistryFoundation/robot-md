"""SP6 Phase 1.5 — rrf.submit_score happy-path tests against urllib mock.

Mirrors the pattern in cli/tests/test_submit.py: patch
`urllib.request.urlopen` with a fake that captures the Request object
and returns a stub response. The §27 wire format is locked in
docs/superpowers/specs/2026-04-26-sp6-spatial-intelligence-eval-design.md
"§27 wire format" subsection.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest

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
    return tmp_path


@pytest.fixture
def with_apikey(home: Path) -> Path:
    apikey_path = home / ".robot-md" / "keys" / "RRN-000000000002.apikey"
    apikey_path.parent.mkdir(parents=True, exist_ok=True)
    apikey_path.write_text("bob-apikey-xyz")
    return apikey_path


def _signed_score() -> ScoreJSON:
    return ScoreJSON(
        spec_version="1.0.0",
        rrn="RRN-000000000002",
        run_id="run-123",
        timestamp="2026-04-30T18:00:00Z",
        tracks_probe=ProbeTrack(
            baseline_claude={"O1": PerUnitProbeScore(score=0.87, n=30, passed=26)},
            robot_declared={"O1": PerUnitProbeScore(score=0.84, n=30, passed=25)},
            delta_per_unit={"O1": -0.03},
        ),
        tracks_execute={
            "O1": PerUnitExecuteScore(passed=7, n=10, evidence_sha256="abc"),
        },
        aggregate=Aggregate(probe_baseline=0.87, probe_declared=0.84, execute=0.7),
        rcan_signature="rcan-sig-base64",
        evidence_root="sha256:e1",
    )


def _mock_response(status: int, body: dict | bytes = b"") -> object:
    class _Resp:
        def __init__(self):
            self.status = status
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            self._fp = io.BytesIO(data)

        def read(self):
            return self._fp.read()

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    return _Resp()


def test_submit_score_posts_to_v1_spatial_eval_runs(with_apikey):
    captured: dict = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["body"] = json.loads(req.data.decode())
        return _mock_response(202, {"submission_id": "sub_x", "status": "pending"})

    from robot_md.spatial_eval.rrf import submit_score

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        submit_score(_signed_score())

    assert captured["url"].endswith("/v1/spatial-eval/runs")
    assert captured["method"] == "POST"


def test_submit_score_wraps_score_under_score_key(with_apikey):
    captured: dict = {}

    def fake_urlopen(req, timeout=None):
        captured["body"] = json.loads(req.data.decode())
        return _mock_response(202, {"submission_id": "sub_x", "status": "pending"})

    from robot_md.spatial_eval.rrf import submit_score

    score = _signed_score()
    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        submit_score(score)

    assert "score" in captured["body"]
    assert captured["body"]["score"]["rrn"] == "RRN-000000000002"
    assert captured["body"]["score"]["rcan_signature"] == "rcan-sig-base64"
    # rrf_signature must be null on submit (RRF fills it in)
    assert captured["body"]["score"]["rrf_signature"] is None


def test_submit_score_sends_bearer_auth_for_score_rrn(with_apikey):
    captured: dict = {}

    def fake_urlopen(req, timeout=None):
        captured["headers"] = dict(req.header_items())
        return _mock_response(202, {"submission_id": "sub_x", "status": "pending"})

    from robot_md.spatial_eval.rrf import submit_score

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        submit_score(_signed_score())

    auth = next((v for k, v in captured["headers"].items() if k.lower() == "authorization"), None)
    assert auth == "Bearer bob-apikey-xyz"


def test_submit_score_returns_pending_status_async_path(with_apikey):
    def fake_urlopen(req, timeout=None):
        return _mock_response(202, {"submission_id": "sub_x", "status": "pending"})

    from robot_md.spatial_eval.rrf import submit_score

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = submit_score(_signed_score())

    assert result["status"] == "pending"
    assert result["submission_id"] == "sub_x"


def test_submit_score_returns_counter_signed_score_sync_path(with_apikey):
    counter_signed_score = _signed_score().to_dict()
    counter_signed_score["rrf_signature"] = "rrf-sig-base64"

    def fake_urlopen(req, timeout=None):
        return _mock_response(
            200,
            {
                "submission_id": "sub_x",
                "status": "counter_signed",
                "score": counter_signed_score,
            },
        )

    from robot_md.spatial_eval.rrf import submit_score

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = submit_score(_signed_score())

    assert result["status"] == "counter_signed"
    assert result["score"]["rrf_signature"] == "rrf-sig-base64"


def test_submit_score_records_audit_entry_on_success(with_apikey, home):
    def fake_urlopen(req, timeout=None):
        return _mock_response(202, {"submission_id": "sub_x", "status": "pending"})

    from robot_md.spatial_eval.rrf import submit_score

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        submit_score(_signed_score())

    audit_log = home / ".robot-md" / "audit" / "RRN-000000000002.jsonl"
    assert audit_log.exists()
    entries = [json.loads(line) for line in audit_log.read_text().splitlines() if line]
    assert any(
        e.get("event") == "submission"
        and e.get("details", {}).get("kind") == "spatial-eval-run"
        and e.get("details", {}).get("outcome") == "ok"
        for e in entries
    )
