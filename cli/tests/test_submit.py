"""Submit-to-RRF helper tests (P2.1).

`submit_artifact` POSTs a signed artifact to /v2/robots/<rrn>/<kind> with
bearer-auth from the keystore. Each successful submit appends an audit
entry. Tests mock urlopen the same way test_rotate_key.py does.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from robot_md.submit import (
    SUPPORTED_KINDS,
    SubmitError,
    submit_artifact,
)


@pytest.fixture
def home(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def with_apikey(home: Path) -> Path:
    apikey_path = home / ".robot-md" / "keys" / "RRN-000000000099.apikey"
    apikey_path.parent.mkdir(parents=True, exist_ok=True)
    apikey_path.write_text("test-bearer-token-xyz")
    return apikey_path


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


def test_supported_kinds_match_rrf_endpoints():
    assert "fria" in SUPPORTED_KINDS
    assert "ifu" in SUPPORTED_KINDS
    assert "safety-benchmark" in SUPPORTED_KINDS
    assert "incident-report" in SUPPORTED_KINDS
    assert "eu-register" in SUPPORTED_KINDS


def test_submit_posts_to_correct_url(with_apikey):
    captured: dict = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["headers"] = dict(req.header_items())
        captured["body"] = json.loads(req.data.decode())
        return _mock_response(200, {"ok": True})

    artifact = {"schema": "rcan-fria-v1", "system": {"rrn": "RRN-000000000099"}}
    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = submit_artifact(artifact, rrn="RRN-000000000099", kind="fria")

    assert captured["url"].endswith("/v2/robots/RRN-000000000099/fria")
    assert captured["method"] == "POST"
    assert captured["body"] == artifact
    assert result["status"] == 200


def test_submit_sends_bearer_auth(with_apikey):
    captured: dict = {}

    def fake_urlopen(req, timeout=None):
        captured["headers"] = dict(req.header_items())
        return _mock_response(200, {"ok": True})

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        submit_artifact({"schema": "rcan-ifu-v1"}, rrn="RRN-000000000099", kind="ifu")

    auth = next((v for k, v in captured["headers"].items() if k.lower() == "authorization"), None)
    assert auth is not None
    assert auth.startswith("Bearer test-bearer-token-")


def test_submit_records_audit_entry(with_apikey, home):
    def fake_urlopen(req, timeout=None):
        return _mock_response(200, {"ok": True})

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        submit_artifact(
            {"schema": "rcan-fria-v1"},
            rrn="RRN-000000000099",
            kind="fria",
        )

    log = home / ".robot-md" / "audit" / "RRN-000000000099.jsonl"
    assert log.exists()
    entry = json.loads(log.read_text().strip().splitlines()[-1])
    assert entry["event"] == "submission"
    assert entry["details"]["kind"] == "fria"
    assert entry["details"]["status"] == 200


def test_submit_records_failed_audit_on_4xx(with_apikey, home):
    """Failed submissions also audit — that's the whole point of an audit log."""
    import urllib.error

    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(
            req.full_url, 403, "Forbidden", {}, io.BytesIO(b'{"error":"nope"}')
        )

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        with pytest.raises(SubmitError, match="403"):
            submit_artifact(
                {"schema": "rcan-fria-v1"},
                rrn="RRN-000000000099",
                kind="fria",
            )

    log = home / ".robot-md" / "audit" / "RRN-000000000099.jsonl"
    entry = json.loads(log.read_text().strip().splitlines()[-1])
    assert entry["details"]["status"] == 403
    assert entry["details"]["outcome"] == "failed"


def test_submit_rejects_unknown_kind(with_apikey):
    with pytest.raises(SubmitError, match="kind"):
        submit_artifact({"schema": "x"}, rrn="RRN-000000000099", kind="unknown-kind")


def test_submit_errors_when_no_apikey(home):
    """No apikey on disk + no api_key arg = clear error."""
    with pytest.raises(SubmitError, match="apikey"):
        submit_artifact({"schema": "rcan-fria-v1"}, rrn="RRN-000000000099", kind="fria")


def test_submit_accepts_explicit_apikey(home):
    """Operator can pass --api-key directly when keystore is empty."""
    captured: dict = {}

    def fake_urlopen(req, timeout=None):
        captured["headers"] = dict(req.header_items())
        return _mock_response(200, {"ok": True})

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        submit_artifact(
            {"schema": "rcan-fria-v1"},
            rrn="RRN-000000000099",
            kind="fria",
            api_key="ad-hoc-token-abc",
        )

    auth = next((v for k, v in captured["headers"].items() if k.lower() == "authorization"), None)
    assert auth == "Bearer ad-hoc-token-abc"
