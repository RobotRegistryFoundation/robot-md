"""v0.9.1 — signing module tests.

Covers keypair gen, save/load roundtrip, kid derivation, canonical-JSON
determinism, sign/verify roundtrip, and cross-language fixture verify
(must accept the same Python-signed fixture that RRF's verify.ts accepts).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import stat
from pathlib import Path

import pytest

from robot_md.signing import (
    SigningKeypair,
    canonical_json,
    generate_keypair,
    kid_from_pub,
    load_keypair,
    save_keypair,
    sign_body,
    verify_body,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "hybrid-fixture.json"
REGISTER_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "register-fixture.json"


def _fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text())


# ---- canonical_json ------------------------------------------------------


def test_canonical_json_sorts_keys():
    out = canonical_json({"b": 2, "a": {"z": 1, "y": 2}})
    assert out == b'{"a":{"y":2,"z":1},"b":2}'


def test_canonical_json_no_whitespace():
    out = canonical_json({"a": 1, "b": 2})
    assert b" " not in out


def test_canonical_json_matches_fixture():
    fx = _fixture()
    expected = base64.b64decode(fx["canonical_bytes_b64"])
    assert canonical_json(fx["body"]) == expected


# ---- kid derivation ------------------------------------------------------


def test_kid_is_8_hex_of_sha256():
    pub = b"\x00" * 1952  # ML-DSA-65 pub size
    kid = kid_from_pub(pub)
    assert kid == hashlib.sha256(pub).hexdigest()[:8]
    assert len(kid) == 8
    assert all(c in "0123456789abcdef" for c in kid)


# ---- generate / save / load ----------------------------------------------


def test_generate_keypair_returns_all_fields():
    kp = generate_keypair()
    assert isinstance(kp, SigningKeypair)
    assert kp.ml_dsa is not None
    assert len(kp.ed25519_pub) == 32
    assert len(kp.ed25519_sec) == 32
    assert len(kp.pq_kid) == 8


def test_save_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    kp = generate_keypair()
    path = save_keypair("RRN-000000000099", kp)
    assert path.exists()
    # File mode must be 600
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode == 0o600, f"got {oct(mode)}"
    # Load and compare
    kp2 = load_keypair("RRN-000000000099")
    assert kp2 is not None
    assert kp2.pq_kid == kp.pq_kid
    assert kp2.ed25519_pub == kp.ed25519_pub
    assert kp2.ed25519_sec == kp.ed25519_sec


def test_load_missing_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert load_keypair("RRN-000000000099") is None


# ---- sign_body / verify_body --------------------------------------------


def test_sign_body_adds_pq_signing_pub_pq_kid_sig():
    kp = generate_keypair()
    body = {"a": 1, "b": "two"}
    signed = sign_body(kp, body)
    assert "pq_signing_pub" in signed
    assert "pq_kid" in signed
    assert "sig" in signed
    assert signed["pq_kid"] == kp.pq_kid
    assert "ml_dsa" in signed["sig"]
    assert "ed25519" in signed["sig"]
    assert "ed25519_pub" in signed["sig"]


def test_sign_body_does_not_mutate_input():
    kp = generate_keypair()
    body = {"a": 1}
    _ = sign_body(kp, body)
    assert body == {"a": 1}


def test_verify_body_accepts_own_signature():
    kp = generate_keypair()
    signed = sign_body(kp, {"a": 1})
    assert verify_body(signed) is True


def test_verify_body_rejects_tampered_ml_dsa():
    kp = generate_keypair()
    signed = sign_body(kp, {"a": 1})
    signed["sig"]["ml_dsa"] = "AAAA" + signed["sig"]["ml_dsa"][4:]
    assert verify_body(signed) is False


def test_verify_body_rejects_tampered_ed25519():
    kp = generate_keypair()
    signed = sign_body(kp, {"a": 1})
    signed["sig"]["ed25519"] = "AAAA" + signed["sig"]["ed25519"][4:]
    assert verify_body(signed) is False


def test_verify_body_rejects_tampered_body_field():
    kp = generate_keypair()
    signed = sign_body(kp, {"a": 1})
    signed["a"] = 999  # tamper
    assert verify_body(signed) is False


# ---- cross-language fixture ---------------------------------------------


def test_cross_language_fixture_primitive_verify():
    """Python verify_hybrid must accept the cross-language hybrid-fixture.

    This tests the primitive verify path (what verify.test.ts also tests),
    NOT the wire format used by sign_body/verify_body — the fixture was
    generated body-only (Task 1 spike), while sign_body uses body+ids.
    """
    from rcan.crypto import HybridSignature, verify_hybrid
    fx = _fixture()
    message = canonical_json(fx["body"])
    verify_hybrid(
        ml_dsa_public_key_bytes=base64.b64decode(fx["pq_signing_pub"]),
        ed25519_public_key_bytes=base64.b64decode(fx["sig"]["ed25519_pub"]),
        message=message,
        hybrid_sig=HybridSignature(
            ml_dsa_sig=base64.b64decode(fx["sig"]["ml_dsa"]),
            ed25519_sig=base64.b64decode(fx["sig"]["ed25519"]),
            kid=fx["pq_kid"],
        ),
    )  # raises on failure; no assertion needed


def test_register_fixture_wire_format_verifies():
    """verify_body accepts a Python-signed body+ids payload — matches the
    exact shape robot-md will POST to RRF /v2/robots/register."""
    fx = json.loads(REGISTER_FIXTURE_PATH.read_text())
    signed = fx["http_body"]
    assert verify_body(signed) is True
