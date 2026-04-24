"""Tests for `robot-md rotate-key` — co-signed key rotation at RRF with local archive.

TDD: tests written before implementation; run pytest to confirm RED, then
implement rotate_key.py to get GREEN.
"""

from __future__ import annotations

import io
import json
import stat
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from robot_md.signing import generate_keypair, kid_from_pub, load_keypair, save_keypair

RRN = "RRN-000000000042"


def _make_keystore(tmp_path: Path) -> Path:
    """Create ~/.robot-md/keys/ under tmp_path and return it."""
    keys_dir = tmp_path / ".robot-md" / "keys"
    keys_dir.mkdir(parents=True)
    return keys_dir


def _save_test_keypair(tmp_path: Path):
    """Generate and save a signing keypair for RRN under tmp HOME. Returns the keypair."""
    kp = generate_keypair()
    save_keypair(RRN, kp)
    return kp


def _mock_200(body: bytes = b'{"ok": true}') -> MagicMock:
    """Build a context-manager mock for a successful 200 HTTP response."""
    resp = MagicMock()
    resp.status = 200
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = lambda *a: None
    return resp


def _http_error(status: int, body: bytes = b"") -> urllib.error.HTTPError:
    """Build an HTTPError with a readable fp."""
    return urllib.error.HTTPError(
        url=f"https://example.com/{RRN}/rotate-key",
        code=status,
        msg="HTTP Error",
        hdrs={},  # type: ignore[arg-type]
        fp=io.BytesIO(body),
    )


# ---------------------------------------------------------------------------
# Test 1: Happy path — 200
# ---------------------------------------------------------------------------


def test_rotate_key_200_success(tmp_path, monkeypatch, capsys):
    """200 from RRF → exit 0, stdout contains 'Rotated', archive path in message, files updated."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _make_keystore(tmp_path)
    old_kp = _save_test_keypair(tmp_path)
    old_kid = kid_from_pub(old_kp.ml_dsa.public_key_bytes)

    from robot_md.rotate_key import cli_rotate_key

    with patch("urllib.request.urlopen", return_value=_mock_200()):
        rc = cli_rotate_key(RRN)

    assert rc == 0
    out = capsys.readouterr().out
    assert "Rotated" in out
    assert "archive" in out.lower()

    # Keystore now has the NEW keypair (different pub bytes)
    new_kp = load_keypair(RRN)
    assert new_kp is not None
    assert new_kp.ml_dsa.public_key_bytes != old_kp.ml_dsa.public_key_bytes

    # Archive file exists with correct name and mode 0600
    archive_path = tmp_path / ".robot-md" / "keys" / "archive" / f"{RRN}.{old_kid}.signing.json"
    assert archive_path.exists(), f"archive not found at {archive_path}"
    file_mode = stat.S_IMODE(archive_path.stat().st_mode)
    assert file_mode == 0o600, f"archive mode is {oct(file_mode)}, expected 0o600"


# ---------------------------------------------------------------------------
# Test 2: Request body shape
# ---------------------------------------------------------------------------


def test_rotate_key_request_body_shape(tmp_path, monkeypatch):
    """POST body has by_old_key and by_new_key; both envelopes have expected fields."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _make_keystore(tmp_path)
    _save_test_keypair(tmp_path)

    captured_body: dict = {}

    def fake_urlopen(req, timeout=15.0):
        captured_body.update(json.loads(req.data.decode("utf-8")))
        return _mock_200()

    from robot_md.rotate_key import cli_rotate_key

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        rc = cli_rotate_key(RRN)

    assert rc == 0

    # Top-level structure
    assert "by_old_key" in captured_body
    assert "by_new_key" in captured_body

    old_env = captured_body["by_old_key"]
    new_env = captured_body["by_new_key"]

    # Both envelopes reference the same canonical payload fields
    for env in (old_env, new_env):
        assert env["rrn"] == RRN
        assert env["action"] == "rotate"
        assert "new_pq_signing_pub" in env
        assert "new_pq_kid" in env
        # sign_body stamps these onto the envelope
        assert "sig" in env
        assert "pq_signing_pub" in env
        assert "pq_kid" in env

    # The two envelopes use different keys — different pq_signing_pub (old vs new key)
    assert old_env["pq_signing_pub"] != new_env["pq_signing_pub"]

    # Both reference the same new key info
    assert old_env["new_pq_signing_pub"] == new_env["new_pq_signing_pub"]
    assert old_env["new_pq_kid"] == new_env["new_pq_kid"]


# ---------------------------------------------------------------------------
# Test 3: 401 — signature rejected
# ---------------------------------------------------------------------------


def test_rotate_key_401_rejected(tmp_path, monkeypatch, capsys):
    """401 from RRF → non-zero exit, keystore UNTOUCHED, archive NOT created."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _make_keystore(tmp_path)
    old_kp = _save_test_keypair(tmp_path)

    body = json.dumps({"error": "Signature verification failed"}).encode()

    from robot_md.rotate_key import cli_rotate_key

    with patch("urllib.request.urlopen", side_effect=_http_error(401, body)):
        rc = cli_rotate_key(RRN)

    assert rc != 0
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "Signature rejected" in combined or "rejected" in combined.lower()

    # Keystore is untouched — still has old keypair
    current_kp = load_keypair(RRN)
    assert current_kp is not None
    assert current_kp.ml_dsa.public_key_bytes == old_kp.ml_dsa.public_key_bytes

    # Archive directory not created
    archive_dir = tmp_path / ".robot-md" / "keys" / "archive"
    assert not archive_dir.exists()


# ---------------------------------------------------------------------------
# Test 4: 403 — record revoked
# ---------------------------------------------------------------------------


def test_rotate_key_403_revoked(tmp_path, monkeypatch, capsys):
    """403 from RRF → non-zero exit, keystore UNTOUCHED, no archive."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _make_keystore(tmp_path)
    old_kp = _save_test_keypair(tmp_path)

    from robot_md.rotate_key import cli_rotate_key

    with patch("urllib.request.urlopen", side_effect=_http_error(403, b"revoked")):
        rc = cli_rotate_key(RRN)

    assert rc != 0
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "revoked" in combined.lower() or RRN in combined

    # Keystore untouched
    current_kp = load_keypair(RRN)
    assert current_kp is not None
    assert current_kp.ml_dsa.public_key_bytes == old_kp.ml_dsa.public_key_bytes

    archive_dir = tmp_path / ".robot-md" / "keys" / "archive"
    assert not archive_dir.exists()


# ---------------------------------------------------------------------------
# Test 5: 404 — not found
# ---------------------------------------------------------------------------


def test_rotate_key_404_not_found(tmp_path, monkeypatch, capsys):
    """404 from RRF → non-zero exit, keystore UNTOUCHED, no archive."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _make_keystore(tmp_path)
    old_kp = _save_test_keypair(tmp_path)

    from robot_md.rotate_key import cli_rotate_key

    with patch("urllib.request.urlopen", side_effect=_http_error(404, b"not found")):
        rc = cli_rotate_key(RRN)

    assert rc != 0
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "not found" in combined.lower()

    # Keystore untouched
    current_kp = load_keypair(RRN)
    assert current_kp is not None
    assert current_kp.ml_dsa.public_key_bytes == old_kp.ml_dsa.public_key_bytes

    archive_dir = tmp_path / ".robot-md" / "keys" / "archive"
    assert not archive_dir.exists()


# ---------------------------------------------------------------------------
# Test 6: No local signing key
# ---------------------------------------------------------------------------


def test_rotate_key_no_signing_key(tmp_path, monkeypatch, capsys):
    """No key for RRN → non-zero exit, no HTTP call attempted."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _make_keystore(tmp_path)
    # Intentionally do NOT save any keypair

    from robot_md.rotate_key import cli_rotate_key

    with patch("urllib.request.urlopen") as mock_urlopen:
        rc = cli_rotate_key(RRN)
        mock_urlopen.assert_not_called()

    assert rc != 0
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert RRN in combined or "signing key" in combined.lower()


# ---------------------------------------------------------------------------
# Test 7: Network error — URLError
# ---------------------------------------------------------------------------


def test_rotate_key_network_error(tmp_path, monkeypatch, capsys):
    """URLError → non-zero exit, keystore UNTOUCHED, no archive."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _make_keystore(tmp_path)
    old_kp = _save_test_keypair(tmp_path)

    from robot_md.rotate_key import cli_rotate_key

    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.URLError("Connection refused"),
    ):
        rc = cli_rotate_key(RRN)

    assert rc != 0

    # Keystore untouched
    current_kp = load_keypair(RRN)
    assert current_kp is not None
    assert current_kp.ml_dsa.public_key_bytes == old_kp.ml_dsa.public_key_bytes

    # No archive
    archive_dir = tmp_path / ".robot-md" / "keys" / "archive"
    assert not archive_dir.exists()


# ---------------------------------------------------------------------------
# Test 8: Archive-write failure — partial state (server rotated, archive failed)
# ---------------------------------------------------------------------------


def test_rotate_key_archive_write_failure(tmp_path, monkeypatch, capsys):
    """If archive-write raises IOError after successful POST, keystore is untouched.

    The server has accepted the rotation but local persistence of the archive failed.
    The implementation must NOT proceed to save the new keypair in this case.
    The old key remains in the keystore so the operator can at least try revoke.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    _make_keystore(tmp_path)
    old_kp = _save_test_keypair(tmp_path)

    def raise_ioerror(rrn, kp):
        raise IOError("disk full")

    from robot_md.rotate_key import cli_rotate_key
    import robot_md.rotate_key as rk_mod

    with patch("urllib.request.urlopen", return_value=_mock_200()):
        with patch.object(rk_mod, "archive_old_keypair", side_effect=raise_ioerror):
            rc = cli_rotate_key(RRN)

    assert rc != 0  # non-zero — something went wrong

    # Keystore still has the OLD keypair — we did not replace it
    current_kp = load_keypair(RRN)
    assert current_kp is not None
    assert current_kp.ml_dsa.public_key_bytes == old_kp.ml_dsa.public_key_bytes

    # Archive directory was not created (the mock raised before any write)
    archive_dir = tmp_path / ".robot-md" / "keys" / "archive"
    assert not archive_dir.exists()
