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


_DEFAULT_MOCK_200_BODY = (
    b'{"verification_status": "manufacturer_claimed",'
    b' "identity_binding": {"type": "dns-txt", "domain": "robotis.com"}}'
)


def _mock_200(body: bytes = _DEFAULT_MOCK_200_BODY) -> MagicMock:
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

    mv_body = (
        b'{"verification_status": "manufacturer_verified",'
        b' "identity_binding": {"type": "attestation"}}'
    )
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


def test_verify_tier_mv_missing_attestation_file_arg(tmp_path, monkeypatch, capsys):
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


def test_verify_tier_mv_attestation_file_not_found(tmp_path, monkeypatch, capsys):
    """manufacturer_verified + missing file: stderr says 'Attestation file not found'."""
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


# ---------------------------------------------------------------------------
# Test 10: 401 — signature rejected
# ---------------------------------------------------------------------------


def test_verify_tier_401_rejected(tmp_path, monkeypatch, capsys):
    """401 from RRF → non-zero exit, error string mentions signature."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _make_keystore(tmp_path)
    _save_test_keypair(tmp_path)

    body = json.dumps({"error": "bad sig"}).encode()

    from robot_md.verify_tier import cli_verify_tier

    with patch("urllib.request.urlopen", side_effect=_http_error(401, body)):
        rc = cli_verify_tier(
            RRN,
            target="manufacturer_claimed",
            dns_domain=DNS_DOMAIN,
            non_interactive=True,
        )

    assert rc != 0
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "Signature rejected" in combined


# ---------------------------------------------------------------------------
# Test 11: 403 — record revoked
# ---------------------------------------------------------------------------


def test_verify_tier_403_revoked(tmp_path, monkeypatch, capsys):
    """403 → non-zero exit, error mentions 'revoked'."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _make_keystore(tmp_path)
    _save_test_keypair(tmp_path)

    from robot_md.verify_tier import cli_verify_tier

    with patch("urllib.request.urlopen", side_effect=_http_error(403, b"")):
        rc = cli_verify_tier(
            RRN,
            target="manufacturer_claimed",
            dns_domain=DNS_DOMAIN,
            non_interactive=True,
        )

    assert rc != 0
    captured = capsys.readouterr()
    assert "revoked" in (captured.out + captured.err).lower()


# ---------------------------------------------------------------------------
# Test 12: 404 — RRN not found
# ---------------------------------------------------------------------------


def test_verify_tier_404_not_found(tmp_path, monkeypatch, capsys):
    """404 → non-zero exit, error mentions 'not found' and the RRN."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _make_keystore(tmp_path)
    _save_test_keypair(tmp_path)

    from robot_md.verify_tier import cli_verify_tier

    with patch("urllib.request.urlopen", side_effect=_http_error(404, b"")):
        rc = cli_verify_tier(
            RRN,
            target="manufacturer_claimed",
            dns_domain=DNS_DOMAIN,
            non_interactive=True,
        )

    assert rc != 0
    combined = capsys.readouterr().err
    assert "not found" in combined.lower()
    assert RRN in combined


# ---------------------------------------------------------------------------
# Test 13: 409 — promotion state conflict
# ---------------------------------------------------------------------------


def test_verify_tier_409_conflict(tmp_path, monkeypatch, capsys):
    """409 from RRF → non-zero exit with 'conflict' in the message."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _make_keystore(tmp_path)
    _save_test_keypair(tmp_path)

    body = json.dumps({"error": "tier is already manufacturer_verified"}).encode()

    from robot_md.verify_tier import cli_verify_tier

    with patch("urllib.request.urlopen", side_effect=_http_error(409, body)):
        rc = cli_verify_tier(
            RRN,
            target="manufacturer_claimed",
            dns_domain=DNS_DOMAIN,
            non_interactive=True,
        )

    assert rc != 0
    combined = capsys.readouterr().err
    assert "conflict" in combined.lower()


# ---------------------------------------------------------------------------
# Test 14: Network error — URLError
# ---------------------------------------------------------------------------


def test_verify_tier_network_error(tmp_path, monkeypatch, capsys):
    """URLError → non-zero exit with 'reach' in the message."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _make_keystore(tmp_path)
    _save_test_keypair(tmp_path)

    from robot_md.verify_tier import cli_verify_tier

    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.URLError("Connection refused"),
    ):
        rc = cli_verify_tier(
            RRN,
            target="manufacturer_claimed",
            dns_domain=DNS_DOMAIN,
            non_interactive=True,
        )

    assert rc != 0
    combined = capsys.readouterr().err
    assert "reach" in combined.lower() or "Could not" in combined


# ---------------------------------------------------------------------------
# Test 15: --yes (non_interactive=True) suppresses prompt even on a TTY
# ---------------------------------------------------------------------------


def test_verify_tier_non_interactive_suppresses_prompt(tmp_path, monkeypatch):
    """non_interactive=True must bypass input() even when stdin is a TTY."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _make_keystore(tmp_path)
    _save_test_keypair(tmp_path)

    import robot_md.verify_tier as vt_mod
    from robot_md.verify_tier import cli_verify_tier

    # Pretend we're running on a real terminal so _is_interactive() would
    # otherwise prompt.
    with (
        patch.object(vt_mod, "_is_interactive", return_value=True),
        patch("builtins.input") as mock_input,
        patch("urllib.request.urlopen", return_value=_mock_200()),
    ):
        rc = cli_verify_tier(
            RRN,
            target="manufacturer_claimed",
            dns_domain=DNS_DOMAIN,
            non_interactive=True,
        )
        mock_input.assert_not_called()

    assert rc == 0


# ---------------------------------------------------------------------------
# Test 16: Interactive mode DOES call input() when non_interactive=False
# ---------------------------------------------------------------------------


def test_verify_tier_interactive_prompts_for_confirmation(tmp_path, monkeypatch):
    """non_interactive=False + TTY → input() is called before the POST."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _make_keystore(tmp_path)
    _save_test_keypair(tmp_path)

    import robot_md.verify_tier as vt_mod
    from robot_md.verify_tier import cli_verify_tier

    with (
        patch.object(vt_mod, "_is_interactive", return_value=True),
        patch("builtins.input", return_value="") as mock_input,
        patch("urllib.request.urlopen", return_value=_mock_200()),
    ):
        rc = cli_verify_tier(
            RRN,
            target="manufacturer_claimed",
            dns_domain=DNS_DOMAIN,
            non_interactive=False,
        )
        mock_input.assert_called_once()

    assert rc == 0


# ---------------------------------------------------------------------------
# Test 17: Oversized attestation file is rejected before parsing
# ---------------------------------------------------------------------------


def test_verify_tier_attestation_file_too_large(tmp_path, monkeypatch, capsys):
    """Attestation file larger than MAX_ATTESTATION_BYTES → exit 1, no HTTP call."""
    monkeypatch.setenv("HOME", str(tmp_path))
    _make_keystore(tmp_path)
    _save_test_keypair(tmp_path)

    from robot_md.verify_tier import MAX_ATTESTATION_BYTES, cli_verify_tier

    # Produce a syntactically-valid but oversized JSON file
    big = tmp_path / "big_attestation.json"
    padding = "x" * (MAX_ATTESTATION_BYTES + 1024)
    big.write_text(json.dumps({"pad": padding}))

    with patch("urllib.request.urlopen") as mock_urlopen:
        rc = cli_verify_tier(
            RRN,
            target="manufacturer_verified",
            dns_domain=DNS_DOMAIN,
            ruri="https://robotis.com",
            attestation_file=big,
            non_interactive=True,
        )
        mock_urlopen.assert_not_called()

    assert rc == 1
    assert "too large" in capsys.readouterr().err.lower()
