"""SP6 Phase 1.5+ — fetch_rrf_pubkey against urllib-mocked GET /v1/spatial-eval/spec/{version}.

Used by verify_tool's production wiring to fetch the RRF ML-DSA public
key for `spec_version` and verify the rrf_signature on counter-signed
scores. Failures are soft — verify_tool falls back to self-attested
with a warning when fetch fails.
"""

from __future__ import annotations

import base64
import io
import json
import urllib.error
from unittest.mock import patch

import pytest


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


def test_fetch_rrf_pubkey_returns_decoded_bytes():
    fake_pubkey = b"\x01\x02\x03\x04" * 488  # ml-dsa-65 pubkey size
    fake_pubkey_b64 = base64.b64encode(fake_pubkey).decode("ascii")

    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        return _mock_response(
            200,
            {
                "spec_version": "1.0.0",
                "rrf_pubkey": fake_pubkey_b64,
                "rrf_pubkey_alg": "ml-dsa-65",
            },
        )

    from robot_md.spatial_eval.rrf import fetch_rrf_pubkey

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = fetch_rrf_pubkey("1.0.0")

    assert result == fake_pubkey
    assert captured["url"].endswith("/v1/spatial-eval/spec/1.0.0")
    assert captured["method"] == "GET"


def test_fetch_rrf_pubkey_raises_on_network_error():
    def fake_urlopen(req, timeout=None):
        raise urllib.error.URLError("Connection refused")

    from robot_md.spatial_eval.rrf import RrfFetchError, fetch_rrf_pubkey

    with (
        patch("urllib.request.urlopen", side_effect=fake_urlopen),
        pytest.raises(RrfFetchError, match="could not fetch"),
    ):
        fetch_rrf_pubkey("1.0.0")


def test_fetch_rrf_pubkey_raises_on_404():
    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", hdrs={}, fp=io.BytesIO(b"{}"))

    from robot_md.spatial_eval.rrf import RrfFetchError, fetch_rrf_pubkey

    with (
        patch("urllib.request.urlopen", side_effect=fake_urlopen),
        pytest.raises(RrfFetchError, match="could not fetch"),
    ):
        fetch_rrf_pubkey("9.9.9")


def test_fetch_rrf_pubkey_raises_on_missing_rrf_pubkey_field():
    def fake_urlopen(req, timeout=None):
        return _mock_response(200, {"spec_version": "1.0.0"})  # no rrf_pubkey

    from robot_md.spatial_eval.rrf import RrfFetchError, fetch_rrf_pubkey

    with (
        patch("urllib.request.urlopen", side_effect=fake_urlopen),
        pytest.raises(RrfFetchError, match="missing rrf_pubkey"),
    ):
        fetch_rrf_pubkey("1.0.0")


def test_fetch_rrf_pubkey_raises_on_malformed_base64():
    def fake_urlopen(req, timeout=None):
        return _mock_response(200, {"spec_version": "1.0.0", "rrf_pubkey": "!!!not-b64"})

    from robot_md.spatial_eval.rrf import RrfFetchError, fetch_rrf_pubkey

    with (
        patch("urllib.request.urlopen", side_effect=fake_urlopen),
        pytest.raises(RrfFetchError, match="not valid base64"),
    ):
        fetch_rrf_pubkey("1.0.0")


def test_fetch_rrf_pubkey_uses_custom_endpoint():
    captured = {}
    fake_pubkey = b"x" * 1952
    fake_pubkey_b64 = base64.b64encode(fake_pubkey).decode("ascii")

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        return _mock_response(200, {"rrf_pubkey": fake_pubkey_b64})

    from robot_md.spatial_eval.rrf import fetch_rrf_pubkey

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        fetch_rrf_pubkey("1.0.0", endpoint="http://localhost:8765")

    assert captured["url"] == "http://localhost:8765/v1/spatial-eval/spec/1.0.0"
