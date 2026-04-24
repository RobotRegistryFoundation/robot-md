"""Tests for `robot-md revoke-key` — signed POST to revoke a robot's signing key.

TDD: tests written before implementation; run pytest to confirm RED, then
implement revoke_key.py to get GREEN.
"""

from __future__ import annotations

import io
import json
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from robot_md.signing import generate_keypair, save_keypair

RRN = "RRN-000000000042"


def _make_keystore(tmp_path: Path) -> Path:
    """Create ~/.robot-md/keys/ under tmp_path and return it."""
    keys_dir = tmp_path / ".robot-md" / "keys"
    keys_dir.mkdir(parents=True)
    return keys_dir


def _save_test_keypair(tmp_path: Path) -> None:
    """Generate and save a signing keypair for RRN under tmp HOME."""
    kp = generate_keypair()
    save_keypair(RRN, kp)


def _mock_200_ish(status: int, body: bytes = b"") -> MagicMock:
    """Build a context-manager mock for a successful (non-error) HTTP response."""
    resp = MagicMock()
    resp.status = status
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = lambda *a: None
    return resp


def _http_error(status: int, body: bytes = b"") -> urllib.error.HTTPError:
    """Build an HTTPError with a readable fp."""
    return urllib.error.HTTPError(
        url=f"https://example.com/{RRN}/revoke-key",
        code=status,
        msg="HTTP Error",
        hdrs={},  # type: ignore[arg-type]
        fp=io.BytesIO(body),
    )


# ---------------------------------------------------------------------------
# Test 1: Happy path — 204
# ---------------------------------------------------------------------------


def test_revoke_key_204_success(tmp_path, monkeypatch, capsys):
    """204 from RRF → exit 0, stdout contains 'Revoked: <rrn>'."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _make_keystore(tmp_path)
    _save_test_keypair(tmp_path)

    mock_resp = _mock_200_ish(204)

    from robot_md.revoke_key import cli_revoke_key

    with patch("urllib.request.urlopen", return_value=mock_resp):
        rc = cli_revoke_key(RRN)

    assert rc == 0
    out = capsys.readouterr().out
    assert "Revoked:" in out
    assert RRN in out


# ---------------------------------------------------------------------------
# Test 2: Already revoked — 409 (idempotent, exit 0)
# ---------------------------------------------------------------------------


def test_revoke_key_409_already_revoked(tmp_path, monkeypatch, capsys):
    """409 from RRF → exit 0 (idempotent), stdout contains 'Already revoked'."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _make_keystore(tmp_path)
    _save_test_keypair(tmp_path)

    from robot_md.revoke_key import cli_revoke_key

    with patch(
        "urllib.request.urlopen",
        side_effect=_http_error(409, b'{"error": "already revoked"}'),
    ):
        rc = cli_revoke_key(RRN)

    assert rc == 0
    out = capsys.readouterr().out
    assert "Already revoked" in out
    assert RRN in out


# ---------------------------------------------------------------------------
# Test 3: Unauthorized — 401
# ---------------------------------------------------------------------------


def test_revoke_key_401_signature_rejected(tmp_path, monkeypatch, capsys):
    """401 from RRF → non-zero exit, message mentions 'Signature rejected'."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _make_keystore(tmp_path)
    _save_test_keypair(tmp_path)

    body = json.dumps({"error": "Signature verification failed"}).encode()

    from robot_md.revoke_key import cli_revoke_key

    with patch(
        "urllib.request.urlopen",
        side_effect=_http_error(401, body),
    ):
        rc = cli_revoke_key(RRN)

    assert rc != 0
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "Signature rejected" in combined


# ---------------------------------------------------------------------------
# Test 4: Not found — 404
# ---------------------------------------------------------------------------


def test_revoke_key_404_not_found(tmp_path, monkeypatch, capsys):
    """404 from RRF → non-zero exit, message mentions 'not found'."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _make_keystore(tmp_path)
    _save_test_keypair(tmp_path)

    from robot_md.revoke_key import cli_revoke_key

    with patch(
        "urllib.request.urlopen",
        side_effect=_http_error(404, b'{"error": "not found"}'),
    ):
        rc = cli_revoke_key(RRN)

    assert rc != 0
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "not found" in combined.lower()


# ---------------------------------------------------------------------------
# Test 5: No local signing key — friendly error, no urlopen call
# ---------------------------------------------------------------------------


def test_revoke_key_no_signing_key(tmp_path, monkeypatch, capsys):
    """When keystore has no signing key for RRN: non-zero exit, friendly message, no HTTP call."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _make_keystore(tmp_path)
    # Intentionally do NOT save any keypair

    from robot_md.revoke_key import cli_revoke_key

    with patch("urllib.request.urlopen") as mock_urlopen:
        rc = cli_revoke_key(RRN)
        mock_urlopen.assert_not_called()

    assert rc != 0
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert RRN in combined
    # Friendly hint that they need to re-register with v0.9.1+
    assert "signing.json" in combined or "v0.9.1" in combined


# ---------------------------------------------------------------------------
# Test 6: Request body shape (with and without --reason)
# ---------------------------------------------------------------------------


def test_revoke_key_body_shape_with_reason(tmp_path, monkeypatch):
    """Signed POST body contains rrn, action, reason, pq_signing_pub, pq_kid, sig."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _make_keystore(tmp_path)
    _save_test_keypair(tmp_path)

    captured_body: dict = {}

    def fake_urlopen(req, timeout=15.0):
        # Parse the sent body
        captured_body.update(json.loads(req.data.decode("utf-8")))
        return _mock_200_ish(204)

    from robot_md.revoke_key import cli_revoke_key

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        rc = cli_revoke_key(RRN, reason="test reason")

    assert rc == 0
    assert captured_body["rrn"] == RRN
    assert captured_body["action"] == "revoke"
    assert captured_body["reason"] == "test reason"
    assert "pq_signing_pub" in captured_body
    assert "pq_kid" in captured_body
    assert "sig" in captured_body


def test_revoke_key_body_shape_without_reason(tmp_path, monkeypatch):
    """When --reason is omitted, the 'reason' key must be absent entirely (not None)."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _make_keystore(tmp_path)
    _save_test_keypair(tmp_path)

    captured_body: dict = {}

    def fake_urlopen(req, timeout=15.0):
        captured_body.update(json.loads(req.data.decode("utf-8")))
        return _mock_200_ish(204)

    from robot_md.revoke_key import cli_revoke_key

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        rc = cli_revoke_key(RRN, reason=None)

    assert rc == 0
    assert captured_body["rrn"] == RRN
    assert captured_body["action"] == "revoke"
    assert "reason" not in captured_body  # key must be absent, not None
    assert "pq_signing_pub" in captured_body
    assert "pq_kid" in captured_body
    assert "sig" in captured_body


# ---------------------------------------------------------------------------
# Test 7: Network error (URLError)
# ---------------------------------------------------------------------------


def test_revoke_key_network_error(tmp_path, monkeypatch, capsys):
    """URLError → non-zero exit, message mentions 'Could not reach'."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _make_keystore(tmp_path)
    _save_test_keypair(tmp_path)

    from robot_md.revoke_key import cli_revoke_key

    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.URLError("Connection refused"),
    ):
        rc = cli_revoke_key(RRN)

    assert rc != 0
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "Could not reach" in combined or "could not reach" in combined.lower()
