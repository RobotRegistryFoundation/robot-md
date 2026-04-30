"""SP6 Phase 1.5 — rrf.poll_status against urllib-mocked GET /v1/spatial-eval/runs/{id}.

Same urllib mock pattern as test_rrf_submit_score.py. Polls a submission
by id; returns one of {pending, counter_signed, rejected}.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def home(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    apikey = tmp_path / ".robot-md" / "keys" / "RRN-000000000002.apikey"
    apikey.parent.mkdir(parents=True, exist_ok=True)
    apikey.write_text("bob-apikey")
    return tmp_path


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


def test_poll_status_gets_runs_submission_id_path(home):
    captured: dict = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        return _mock_response(200, {"submission_id": "sub_x", "status": "pending"})

    from robot_md.spatial_eval.rrf import poll_status

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        poll_status("sub_x", rrn="RRN-000000000002")

    assert captured["url"].endswith("/v1/spatial-eval/runs/sub_x")
    assert captured["method"] == "GET"


def test_poll_status_sends_bearer_auth(home):
    captured: dict = {}

    def fake_urlopen(req, timeout=None):
        captured["headers"] = dict(req.header_items())
        return _mock_response(200, {"submission_id": "sub_x", "status": "pending"})

    from robot_md.spatial_eval.rrf import poll_status

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        poll_status("sub_x", rrn="RRN-000000000002")

    auth = next(
        (v for k, v in captured["headers"].items() if k.lower() == "authorization"), None
    )
    assert auth == "Bearer bob-apikey"


def test_poll_status_returns_pending(home):
    def fake_urlopen(req, timeout=None):
        return _mock_response(200, {"submission_id": "sub_x", "status": "pending"})

    from robot_md.spatial_eval.rrf import poll_status

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = poll_status("sub_x", rrn="RRN-000000000002")

    assert result["status"] == "pending"
    assert result["submission_id"] == "sub_x"


def test_poll_status_returns_counter_signed_with_score(home):
    counter_signed = {
        "submission_id": "sub_x",
        "status": "counter_signed",
        "score": {"rrn": "RRN-000000000002", "rrf_signature": "rrf-sig"},
    }

    def fake_urlopen(req, timeout=None):
        return _mock_response(200, counter_signed)

    from robot_md.spatial_eval.rrf import poll_status

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = poll_status("sub_x", rrn="RRN-000000000002")

    assert result["status"] == "counter_signed"
    assert result["score"]["rrf_signature"] == "rrf-sig"


def test_poll_status_returns_rejected_with_reason(home):
    rejected = {
        "submission_id": "sub_x",
        "status": "rejected",
        "rejection_reason": "rcan_signature failed verification",
    }

    def fake_urlopen(req, timeout=None):
        return _mock_response(200, rejected)

    from robot_md.spatial_eval.rrf import poll_status

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = poll_status("sub_x", rrn="RRN-000000000002")

    assert result["status"] == "rejected"
    assert "rcan_signature" in result["rejection_reason"]


def test_poll_status_records_audit_entry_on_success(home):
    def fake_urlopen(req, timeout=None):
        return _mock_response(200, {"submission_id": "sub_x", "status": "pending"})

    from robot_md.spatial_eval.rrf import poll_status

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        poll_status("sub_x", rrn="RRN-000000000002")

    audit_log = home / ".robot-md" / "audit" / "RRN-000000000002.jsonl"
    assert audit_log.exists()
    entries = [json.loads(line) for line in audit_log.read_text().splitlines() if line]
    assert any(
        e.get("event") == "submission"
        and e.get("details", {}).get("kind") == "spatial-eval-poll"
        and e.get("details", {}).get("outcome") == "ok"
        for e in entries
    )
