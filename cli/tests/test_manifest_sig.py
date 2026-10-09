"""Tests for robot-md manifest provenance-footer signing (manifest_sig)."""

from __future__ import annotations

import base64

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from robot_md.manifest_sig import (
    _SIG_RE,
    signed_manifest_text,
    strip_footer,
    verify_manifest_text,
)

BODY = "---\nmetadata:\n  rrn: RRN-000000000011\n---\n# robot\n\nsome body.\n"


def test_sign_then_verify_roundtrip():
    priv = Ed25519PrivateKey.generate()
    signed = signed_manifest_text(BODY, priv, kid="bob-operator-2026")
    ok, kid = verify_manifest_text(signed, priv.public_key())
    assert ok
    assert kid == "bob-operator-2026"


def test_footer_format_and_signature_length():
    priv = Ed25519PrivateKey.generate()
    signed = signed_manifest_text(BODY, priv, kid="op-2026")
    match = _SIG_RE.search(signed)
    assert match is not None
    assert match.group("kid") == "op-2026"
    # Ed25519 signatures are exactly 64 bytes.
    assert len(base64.b64decode(match.group("sig"))) == 64


def test_signed_preimage_is_text_before_footer():
    """The gateway verifies over `text[: match.start()]`; our sig must match that."""
    priv = Ed25519PrivateKey.generate()
    signed = signed_manifest_text(BODY, priv, kid="op")
    match = _SIG_RE.search(signed)
    pre = signed[: match.start()].encode("utf-8")
    # Raises InvalidSignature if our signed pre-image differs from the gateway's.
    priv.public_key().verify(base64.b64decode(match.group("sig")), pre)


def test_resign_is_idempotent_single_footer():
    priv = Ed25519PrivateKey.generate()
    once = signed_manifest_text(BODY, priv, kid="op")
    twice = signed_manifest_text(once, priv, kid="op")
    assert twice.count("ROBOT-MD-SIG") == 1
    ok, _ = verify_manifest_text(twice, priv.public_key())
    assert ok


def test_strip_footer():
    priv = Ed25519PrivateKey.generate()
    signed = signed_manifest_text(BODY, priv, kid="op")
    assert "ROBOT-MD-SIG" not in strip_footer(signed)
    # No-op on an unsigned manifest.
    assert strip_footer(BODY) == BODY


def test_tamper_body_fails_verify():
    priv = Ed25519PrivateKey.generate()
    signed = signed_manifest_text(BODY, priv, kid="op")
    tampered = signed.replace("# robot", "# EVIL", 1)
    ok, reason = verify_manifest_text(tampered, priv.public_key())
    assert not ok
    assert "did not verify" in reason


def test_wrong_key_fails_verify():
    priv = Ed25519PrivateKey.generate()
    signed = signed_manifest_text(BODY, priv, kid="op")
    other_pub = Ed25519PrivateKey.generate().public_key()
    ok, _ = verify_manifest_text(signed, other_pub)
    assert not ok


def test_missing_footer_reason():
    ok, reason = verify_manifest_text(BODY, Ed25519PrivateKey.generate().public_key())
    assert not ok
    assert "no ROBOT-MD-SIG footer" in reason
