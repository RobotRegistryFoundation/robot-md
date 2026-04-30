"""SP6 Phase 1.5 — failure paths for rrf.submit_score and rrf.poll_status.

Covers: missing apikey, RRF down (URLError), 4xx body, audit-trail
preservation across every failure mode.
"""

from __future__ import annotations

import io
import json
import urllib.error
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
def home_no_apikey(tmp_path: Path, monkeypatch) -> Path:
    """HOME pointed at tmp_path without any keystore — apikey lookup fails."""
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def home_with_apikey(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    apikey = tmp_path / ".robot-md" / "keys" / "RRN-000000000002.apikey"
    apikey.parent.mkdir(parents=True, exist_ok=True)
    apikey.write_text("bob-apikey")
    return tmp_path


def _signed_score() -> ScoreJSON:
    return ScoreJSON(
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
    )


def test_submit_score_missing_apikey_raises(home_no_apikey):
    from robot_md.spatial_eval.rrf import RrfSubmitError, submit_score

    with pytest.raises(RrfSubmitError, match="no apikey"):
        submit_score(_signed_score())


def test_submit_score_rrf_down_raises_and_records_audit(home_with_apikey):
    def fake_urlopen(req, timeout=None):
        raise urllib.error.URLError("Connection refused")

    from robot_md.spatial_eval.rrf import RrfSubmitError, submit_score

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        with pytest.raises(RrfSubmitError, match="could not reach"):
            submit_score(_signed_score())

    audit_log = home_with_apikey / ".robot-md" / "audit" / "RRN-000000000002.jsonl"
    entries = [json.loads(line) for line in audit_log.read_text().splitlines() if line]
    assert any(
        e["details"].get("outcome") == "network_error"
        and e["details"].get("kind") == "spatial-eval-run"
        for e in entries
    )


def test_submit_score_4xx_raises_and_records_audit(home_with_apikey):
    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(
            req.full_url,
            422,
            "Unprocessable Entity",
            hdrs={},
            fp=io.BytesIO(b'{"error": "rcan_signature failed verification"}'),
        )

    from robot_md.spatial_eval.rrf import RrfSubmitError, submit_score

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        with pytest.raises(RrfSubmitError, match="returned 422"):
            submit_score(_signed_score())

    audit_log = home_with_apikey / ".robot-md" / "audit" / "RRN-000000000002.jsonl"
    entries = [json.loads(line) for line in audit_log.read_text().splitlines() if line]
    assert any(
        e["details"].get("outcome") == "failed" and e["details"].get("status") == 422
        for e in entries
    )


def test_poll_status_missing_apikey_raises(home_no_apikey):
    from robot_md.spatial_eval.rrf import RrfSubmitError, poll_status

    with pytest.raises(RrfSubmitError, match="no apikey"):
        poll_status("sub_x", rrn="RRN-000000000002")


def test_poll_status_404_raises_and_records_audit(home_with_apikey):
    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(
            req.full_url,
            404,
            "Not Found",
            hdrs={},
            fp=io.BytesIO(b'{"error": "submission_id unknown"}'),
        )

    from robot_md.spatial_eval.rrf import RrfSubmitError, poll_status

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        with pytest.raises(RrfSubmitError, match="returned 404"):
            poll_status("sub_x", rrn="RRN-000000000002")

    audit_log = home_with_apikey / ".robot-md" / "audit" / "RRN-000000000002.jsonl"
    entries = [json.loads(line) for line in audit_log.read_text().splitlines() if line]
    assert any(
        e["details"].get("outcome") == "failed" and e["details"].get("status") == 404
        for e in entries
    )


def test_poll_status_rrf_down_raises_and_records_audit(home_with_apikey):
    def fake_urlopen(req, timeout=None):
        raise urllib.error.URLError("Network unreachable")

    from robot_md.spatial_eval.rrf import RrfSubmitError, poll_status

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        with pytest.raises(RrfSubmitError, match="could not reach"):
            poll_status("sub_x", rrn="RRN-000000000002")

    audit_log = home_with_apikey / ".robot-md" / "audit" / "RRN-000000000002.jsonl"
    entries = [json.loads(line) for line in audit_log.read_text().splitlines() if line]
    assert any(
        e["details"].get("outcome") == "network_error"
        and e["details"].get("kind") == "spatial-eval-poll"
        for e in entries
    )
