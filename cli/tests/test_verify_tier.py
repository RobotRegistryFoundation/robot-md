"""Tests for `robot-md verify-tier` — signed POST to promote a robot's verification tier.

TDD: tests written before implementation; run pytest to confirm RED, then
implement verify_tier.py to get GREEN.
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
DNS_DOMAIN = "robotis.com"


def _make_keystore(tmp_path: Path) -> Path:
    """Create ~/.robot-md/keys/ under tmp_path and return it."""
    keys_dir = tmp_path / ".robot-md" / "keys"
    keys_dir.mkdir(parents=True)
    return keys_dir


def _save_test_keypair(tmp_path: Path) -> None:
    """Generate and save a signing keypair for RRN under tmp HOME."""
    kp = generate_keypair()
    save_keypair(RRN, kp)


def _mock_200(body: bytes = b'{"verification_status": "manufacturer_claimed", "identity_binding": {"type": "dns-txt", "domain": "robotis.com"}}') -> MagicMock:
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
        url=f"https://example.com/{RRN}/verify-tier",
        code=status,
        msg="HTTP Error",
        hdrs={},  # type: ignore[arg-type]
        fp=io.BytesIO(body),
    )


# ---------------------------------------------------------------------------
# Test 1: manufacturer_claimed happy path (200)
# ---------------------------------------------------------------------------


def test_verify_tier_manufacturer_claimed_200_success(tmp_path, monkeypatch, capsys):
    """200 from RRF → exit 0; stdout contains 'Promoted' and 'manufacturer_claimed'."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _make_keystore(tmp_path)
    _save_test_keypair(tmp_path)

    from robot_md.verify_tier import cli_verify_tier

    with patch("urllib.request.urlopen", return_value=_mock_200()):
        rc = cli_verify_tier(
            RRN,
            target="manufacturer_claimed",
            dns_domain=DNS_DOMAIN,
            non_interactive=True,
        )

    assert rc == 0
    out = capsys.readouterr().out
    assert "Promoted" in out
    assert "manufacturer_claimed" in out


# ---------------------------------------------------------------------------
# Test 2: manufacturer_verified happy path (200)
# ---------------------------------------------------------------------------


def test_verify_tier_manufacturer_verified_200_success(tmp_path, monkeypatch, capsys):
    """200 from RRF with manufacturer_verified → exit 0; stdout contains 'manufacturer_verified'."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _make_keystore(tmp_path)
    _save_test_keypair(tmp_path)

    # Write a fake attestation JSON file
    attestation_data = {"type": "rcan-attestation-v1", "rrn": RRN, "sig": "fakesig"}
    attestation_file = tmp_path / "attestation.json"
    attestation_file.write_text(json.dumps(attestation_data))

    from robot_md.verify_tier import cli_verify_tier

    mv_body = b'{"verification_status": "manufacturer_verified", "identity_binding": {"type": "attestation"}}'
    with patch("urllib.request.urlopen", return_value=_mock_200(body=mv_body)):
        rc = cli_verify_tier(
            RRN,
            target="manufacturer_verified",
            dns_domain=DNS_DOMAIN,
            ruri="https://robotis.com",
            attestation_file=attestation_file,
            non_interactive=True,
        )

    assert rc == 0
    out = capsys.readouterr().out
    assert "manufacturer_verified" in out


# ---------------------------------------------------------------------------
# Test 3: Request body shape for manufacturer_claimed
# ---------------------------------------------------------------------------


def test_verify_tier_body_shape_manufacturer_claimed(tmp_path, monkeypatch):
    """Body has rrn, action, target_tier, binding; no ruri, no attestation."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _make_keystore(tmp_path)
    _save_test_keypair(tmp_path)

    captured_body: dict = {}

    def fake_urlopen(req, timeout=30.0):
        captured_body.update(json.loads(req.data.decode("utf-8")))
        return _mock_200()

    from robot_md.verify_tier import cli_verify_tier

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        rc = cli_verify_tier(
            RRN,
            target="manufacturer_claimed",
            dns_domain=DNS_DOMAIN,
            non_interactive=True,
        )

    assert rc == 0
    assert captured_body["rrn"] == RRN
    assert captured_body["action"] == "verify-tier"
    assert captured_body["target_tier"] == "manufacturer_claimed"
    assert captured_body["binding"] == {"type": "dns-txt", "value": DNS_DOMAIN}
    # sign_body stamps these
    assert "sig" in captured_body
    assert "pq_signing_pub" in captured_body
    assert "pq_kid" in captured_body
    # No ruri or attestation
    assert "ruri" not in captured_body
    assert "attestation" not in captured_body


# ---------------------------------------------------------------------------
# Test 4: Request body shape for manufacturer_verified
# ---------------------------------------------------------------------------


def test_verify_tier_body_shape_manufacturer_verified(tmp_path, monkeypatch):
    """Body additionally has ruri and attestation (verbatim dict from file)."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _make_keystore(tmp_path)
    _save_test_keypair(tmp_path)

    attestation_data = {"type": "rcan-attestation-v1", "rrn": RRN, "sig": "fakesig"}
    attestation_file = tmp_path / "attestation.json"
    attestation_file.write_text(json.dumps(attestation_data))

    captured_body: dict = {}

    def fake_urlopen(req, timeout=30.0):
        captured_body.update(json.loads(req.data.decode("utf-8")))
        return _mock_200()

    from robot_md.verify_tier import cli_verify_tier

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        rc = cli_verify_tier(
            RRN,
            target="manufacturer_verified",
            dns_domain=DNS_DOMAIN,
            ruri="https://robotis.com",
            attestation_file=attestation_file,
            non_interactive=True,
        )

    assert rc == 0
    assert captured_body["rrn"] == RRN
    assert captured_body["action"] == "verify-tier"
    assert captured_body["target_tier"] == "manufacturer_verified"
    assert captured_body["binding"] == {"type": "dns-txt", "value": DNS_DOMAIN}
    assert captured_body["ruri"] == "https://robotis.com"
    assert captured_body["attestation"] == attestation_data


# ---------------------------------------------------------------------------
# Test 5: Reject community target
# ---------------------------------------------------------------------------


def test_verify_tier_reject_community(tmp_path, monkeypatch, capsys):
    """community tier → exit non-zero; message mentions 'maintainer-curated'; no HTTP call."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _make_keystore(tmp_path)
    _save_test_keypair(tmp_path)

    from robot_md.verify_tier import cli_verify_tier

    with patch("urllib.request.urlopen") as mock_urlopen:
        rc = cli_verify_tier(
            RRN,
            target="community",
            dns_domain=DNS_DOMAIN,
            non_interactive=True,
        )
        mock_urlopen.assert_not_called()

    assert rc != 0
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "maintainer-curated" in combined


# ---------------------------------------------------------------------------
# Test 6: manufacturer_verified without --attestation-file
# ---------------------------------------------------------------------------


def test_verify_tier_manufacturer_verified_missing_attestation_file_arg(tmp_path, monkeypatch, capsys):
    """manufacturer_verified without attestation_file → exit non-zero; no HTTP call."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _make_keystore(tmp_path)
    _save_test_keypair(tmp_path)

    from robot_md.verify_tier import cli_verify_tier

    with patch("urllib.request.urlopen") as mock_urlopen:
        rc = cli_verify_tier(
            RRN,
            target="manufacturer_verified",
            dns_domain=DNS_DOMAIN,
            ruri="https://robotis.com",
            attestation_file=None,  # missing
            non_interactive=True,
        )
        mock_urlopen.assert_not_called()

    assert rc != 0
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "attestation" in combined.lower() or "manufacturer_verified" in combined


# ---------------------------------------------------------------------------
# Test 7: manufacturer_verified with missing attestation file on disk
# ---------------------------------------------------------------------------


def test_verify_tier_manufacturer_verified_attestation_file_not_found(tmp_path, monkeypatch, capsys):
    """manufacturer_verified with a non-existent file → exit non-zero; message about 'Attestation file not found'."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _make_keystore(tmp_path)
    _save_test_keypair(tmp_path)

    missing_file = tmp_path / "does_not_exist.json"

    from robot_md.verify_tier import cli_verify_tier

    with patch("urllib.request.urlopen") as mock_urlopen:
        rc = cli_verify_tier(
            RRN,
            target="manufacturer_verified",
            dns_domain=DNS_DOMAIN,
            ruri="https://robotis.com",
            attestation_file=missing_file,
            non_interactive=True,
        )
        mock_urlopen.assert_not_called()

    assert rc != 0
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "Attestation file not found" in combined


# ---------------------------------------------------------------------------
# Test 8: 400 RRF response
# ---------------------------------------------------------------------------


def test_verify_tier_400_rrf_rejected(tmp_path, monkeypatch, capsys):
    """400 from RRF → exit non-zero; message contains 'RRF rejected' and the error detail."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _make_keystore(tmp_path)
    _save_test_keypair(tmp_path)

    error_body = json.dumps({"error": "DNS verification failed: TXT record not found"}).encode()

    from robot_md.verify_tier import cli_verify_tier

    with patch(
        "urllib.request.urlopen",
        side_effect=_http_error(400, error_body),
    ):
        rc = cli_verify_tier(
            RRN,
            target="manufacturer_claimed",
            dns_domain=DNS_DOMAIN,
            non_interactive=True,
        )

    assert rc != 0
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "RRF rejected" in combined
    assert "DNS verification failed: TXT record not found" in combined


# ---------------------------------------------------------------------------
# Test 9: No local signing key
# ---------------------------------------------------------------------------


def test_verify_tier_no_signing_key(tmp_path, monkeypatch, capsys):
    """No signing key for RRN → exit non-zero; no HTTP call."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _make_keystore(tmp_path)
    # Intentionally do NOT save any keypair

    from robot_md.verify_tier import cli_verify_tier

    with patch("urllib.request.urlopen") as mock_urlopen:
        rc = cli_verify_tier(
            RRN,
            target="manufacturer_claimed",
            dns_domain=DNS_DOMAIN,
            non_interactive=True,
        )
        mock_urlopen.assert_not_called()

    assert rc != 0
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert RRN in combined or "signing key" in combined.lower()
