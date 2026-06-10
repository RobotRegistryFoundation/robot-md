"""Cross-repo provenance test: the robot-md signer must produce a footer the
robot-md-gateway verifier accepts. Hardware-free."""

from __future__ import annotations

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

# The actual gateway verifier — the contract we must satisfy.
from robot_md_gateway.manifest_provenance import verify_manifest

from robot_md import provenance, signing

SAMPLE = """---
rcan_version: "1.0"
metadata:
  robot_name: bob
  rrn: RRN-000000000011
---

# Bob

Some prose body.
"""


class _StubResolver:
    """Returns the Ed25519 PEM for one kid; mimics the RRF /v2/keys lookup."""

    def __init__(self, kid: str, pub_raw: bytes):
        self._kid = kid
        self._pem = Ed25519PublicKey.from_public_bytes(pub_raw).public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )

    def resolve_public_key_pem(self, kid: str) -> bytes | None:
        return self._pem if kid == self._kid else None


def _kp():
    return signing.generate_keypair()


def test_signed_footer_verifies_against_gateway(tmp_path):
    kp = _kp()
    signed = provenance.sign_manifest_footer(SAMPLE, kp)
    p = tmp_path / "ROBOT.md"
    p.write_text(signed)
    res = verify_manifest(p, resolver=_StubResolver(kp.pq_kid, kp.ed25519_pub))
    assert res.accepted, res.reason
    assert res.kid == kp.pq_kid


def test_resign_is_idempotent_over_existing_footer(tmp_path):
    kp = _kp()
    once = provenance.sign_manifest_footer(SAMPLE, kp)
    twice = provenance.sign_manifest_footer(once, kp)  # strip old footer, re-sign
    p = tmp_path / "ROBOT.md"
    p.write_text(twice)
    # exactly one footer, and it verifies
    assert twice.count("ROBOT-MD-SIG") == 1
    assert verify_manifest(p, resolver=_StubResolver(kp.pq_kid, kp.ed25519_pub)).accepted


def test_tampered_body_fails_verification(tmp_path):
    kp = _kp()
    signed = provenance.sign_manifest_footer(SAMPLE, kp)
    tampered = signed.replace("Some prose body.", "Some TAMPERED body.")
    p = tmp_path / "ROBOT.md"
    p.write_text(tampered)
    res = verify_manifest(p, resolver=_StubResolver(kp.pq_kid, kp.ed25519_pub))
    assert not res.accepted


def test_resign_and_deploy_writes_both_with_backup(tmp_path, monkeypatch):
    kp = _kp()
    monkeypatch.setattr(provenance, "load_keypair", lambda rrn: kp)
    working = tmp_path / "ROBOT.md"
    working.write_text(SAMPLE)
    gateway = tmp_path / "etc" / "ROBOT.md"
    gateway.parent.mkdir(parents=True)
    gateway.write_text("old enforced manifest\n")

    res = provenance.resign_and_deploy(working, rrn="RRN-000000000011", deploy_path=gateway)
    assert res["signed"] and res["deployed"]
    assert res["backup"] is not None  # prior enforced copy was backed up
    resolver = _StubResolver(kp.pq_kid, kp.ed25519_pub)
    assert verify_manifest(working, resolver=resolver).accepted
    assert verify_manifest(gateway, resolver=resolver).accepted
    # working and enforced copies are byte-identical (no drift)
    assert working.read_text() == gateway.read_text()


def test_resign_no_deploy(tmp_path, monkeypatch):
    kp = _kp()
    monkeypatch.setattr(provenance, "load_keypair", lambda rrn: kp)
    working = tmp_path / "ROBOT.md"
    working.write_text(SAMPLE)
    res = provenance.resign_and_deploy(working, rrn="RRN-x", deploy=False)
    assert res["signed"] and not res["deployed"]
    assert verify_manifest(working, resolver=_StubResolver(kp.pq_kid, kp.ed25519_pub)).accepted


def test_missing_keypair_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("ROBOT_MD_OPERATOR_KEY_PATH", raising=False)
    monkeypatch.delenv("ROBOT_MD_OPERATOR_KID", raising=False)
    monkeypatch.setattr(provenance, "load_keypair", lambda rrn: None)
    working = tmp_path / "ROBOT.md"
    working.write_text(SAMPLE)
    with pytest.raises(RuntimeError, match="no signing keypair"):
        provenance.resign_and_deploy(working, rrn="RRN-x")


def _operator_pem(tmp_path):
    """Generate an Ed25519 operator key: returns (pem_path, raw_pub_bytes)."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    priv = Ed25519PrivateKey.generate()
    pem = priv.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    p = tmp_path / "operator.priv.pem"
    p.write_bytes(pem)
    raw_pub = priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return p, raw_pub


def test_footer_signed_with_operator_pem_verifies_against_gateway(tmp_path):
    """sign_manifest_footer must accept a raw operator Ed25519 key + explicit kid and
    sign the SAME core bytes — the footer must verify against the real gateway verifier."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key_path, raw_pub = _operator_pem(tmp_path)
    from cryptography.hazmat.primitives import serialization as _ser

    priv = _ser.load_pem_private_key(key_path.read_bytes(), password=None)
    assert isinstance(priv, Ed25519PrivateKey)
    signed = provenance.sign_manifest_footer(SAMPLE, priv_key=priv, kid="bob-operator-2026")
    p = tmp_path / "ROBOT.md"
    p.write_text(signed)
    res = verify_manifest(p, resolver=_StubResolver("bob-operator-2026", raw_pub))
    assert res.accepted, res.reason
    assert res.kid == "bob-operator-2026"


def test_resign_and_deploy_uses_operator_key_from_env(tmp_path, monkeypatch):
    """When ROBOT_MD_OPERATOR_KEY_PATH/KID are set, resign_and_deploy footer-signs with
    that operator key/kid (the RRF-registered identity) and does NOT need a robot keypair."""
    key_path, raw_pub = _operator_pem(tmp_path)
    # The robot keypair is absent — the operator path must not fall back to it.
    monkeypatch.setattr(provenance, "load_keypair", lambda rrn: None)
    monkeypatch.setenv("ROBOT_MD_OPERATOR_KEY_PATH", str(key_path))
    monkeypatch.setenv("ROBOT_MD_OPERATOR_KID", "bob-operator-2026")
    working = tmp_path / "ROBOT.md"
    working.write_text(SAMPLE)
    gateway = tmp_path / "etc" / "ROBOT.md"
    gateway.parent.mkdir(parents=True)
    gateway.write_text("old enforced manifest\n")

    res = provenance.resign_and_deploy(working, rrn="RRN-000000000011", deploy_path=gateway)
    assert res["signed"] and res["deployed"]
    assert res["kid"] == "bob-operator-2026"
    resolver = _StubResolver("bob-operator-2026", raw_pub)
    assert verify_manifest(working, resolver=resolver).accepted
    assert verify_manifest(gateway, resolver=resolver).accepted
    assert working.read_text() == gateway.read_text()


def test_resign_partial_operator_env_raises(tmp_path, monkeypatch):
    """Half-set operator env -> fail loud, not silent footer-sign with the robot pq_kid."""
    monkeypatch.setenv("ROBOT_MD_OPERATOR_KID", "bob-operator-2026")
    monkeypatch.delenv("ROBOT_MD_OPERATOR_KEY_PATH", raising=False)
    working = tmp_path / "ROBOT.md"
    working.write_text(SAMPLE)
    with pytest.raises(RuntimeError, match="partial operator-key config"):
        provenance.resign_and_deploy(working, rrn="RRN-x", deploy=False)
