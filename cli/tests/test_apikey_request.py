"""Tests for `robot-md request-apikey` (apikey reissue request flow).

The flow lets an operator who holds the *signing keypair* but lost the
*apikey* for an existing RRN produce a cryptographically-signed reissue
request. The signature is the auth — RRF (or admins reading the file
out-of-band) verify against the registered pq_signing_pub.

The server-side endpoint at /v2/robots/<rrn>/apikey-requests doesn't
exist yet — probed 2026-04-25, all paths return SPA fallback. The client
is still useful: it produces signed evidence the operator can hand to
RRF support out-of-band until the endpoint lands.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from robot_md.apikey_request import (
    APIKEY_REQUEST_SCHEMA,
    SubmitError,
    build_request,
    sign_request,
    submit_request,
)


@pytest.fixture
def home(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
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


# ---- build ---------------------------------------------------------------


def test_build_request_includes_schema_and_required_fields():
    req = build_request(rrn="RRN-000000000099")
    assert req["schema"] == APIKEY_REQUEST_SCHEMA
    for field in ("rrn", "operation", "generated_at", "nonce"):
        assert field in req


def test_build_request_default_operation_is_reissue():
    req = build_request(rrn="RRN-000000000099")
    assert req["operation"] == "reissue"


def test_build_request_includes_reason_when_supplied():
    req = build_request(rrn="RRN-000000000099", reason="lost original apikey")
    assert req["reason"] == "lost original apikey"


def test_build_request_omits_reason_when_not_supplied():
    req = build_request(rrn="RRN-000000000099")
    assert "reason" not in req or req["reason"] in (None, "")


def test_build_request_nonces_are_unique():
    a = build_request(rrn="RRN-000000000099")
    b = build_request(rrn="RRN-000000000099")
    assert a["nonce"] != b["nonce"]


def test_build_request_rejects_unknown_operation():
    with pytest.raises(ValueError, match="operation"):
        build_request(rrn="RRN-000000000099", operation="bogus")


# ---- sign ----------------------------------------------------------------


def test_sign_request_requires_keystore(home):
    req = build_request(rrn="RRN-000000000099")
    with pytest.raises(RuntimeError, match="no signing keypair"):
        sign_request(req, rrn="RRN-000000000099")


def test_sign_request_produces_signed_envelope(home):
    """When a signing keypair exists, the signed request includes pq_signing_pub
    + pq_kid + sig. Same wire shape as register/IFU/FRIA artifacts."""
    from robot_md.signing import generate_keypair, save_keypair

    kp = generate_keypair()
    save_keypair("RRN-000000000099", kp)

    req = build_request(rrn="RRN-000000000099")
    signed = sign_request(req, rrn="RRN-000000000099")

    for field in ("pq_signing_pub", "pq_kid", "sig"):
        assert field in signed, f"signed envelope missing {field}"
    # Original payload preserved
    assert signed["schema"] == APIKEY_REQUEST_SCHEMA
    assert signed["rrn"] == "RRN-000000000099"


# ---- submit --------------------------------------------------------------


def test_submit_posts_to_apikey_requests_endpoint(home):
    captured: dict = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["body"] = json.loads(req.data.decode())
        return _mock_response(202, {"status": "queued"})

    signed = {
        "schema": APIKEY_REQUEST_SCHEMA,
        "rrn": "RRN-000000000099",
        "sig": {"x": "y"},
        "pq_signing_pub": "abc",
    }
    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = submit_request(signed, rrn="RRN-000000000099")

    assert captured["url"].endswith("/v2/robots/RRN-000000000099/apikey-requests")
    assert captured["method"] == "POST"
    assert captured["body"] == signed
    assert result["status"] == 202


def test_submit_records_audit_entry_on_success(home):
    from robot_md.audit import load_entries

    def fake_urlopen(req, timeout=None):
        return _mock_response(202, {"queued": True})

    signed = {"schema": APIKEY_REQUEST_SCHEMA, "rrn": "RRN-000000000099"}
    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        submit_request(signed, rrn="RRN-000000000099")

    entries = load_entries("RRN-000000000099")
    assert len(entries) == 1
    assert entries[0]["event"] == "apikey_request"
    assert entries[0]["details"]["status"] == 202
    assert entries[0]["details"]["outcome"] == "ok"


def test_submit_records_audit_on_failure(home):
    """Failed submits also audit — same property as P2's submit_artifact."""
    import urllib.error

    from robot_md.audit import load_entries

    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(
            req.full_url, 404, "Not Found", {}, io.BytesIO(b'{"error":"endpoint not implemented"}')
        )

    signed = {"schema": APIKEY_REQUEST_SCHEMA, "rrn": "RRN-000000000099"}
    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        with pytest.raises(SubmitError, match="404"):
            submit_request(signed, rrn="RRN-000000000099")

    entries = load_entries("RRN-000000000099")
    assert entries[0]["details"]["status"] == 404
    assert entries[0]["details"]["outcome"] == "failed"
