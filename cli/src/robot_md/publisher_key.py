"""Auto-mint + load PQ-hybrid keypairs for `robot-md actuator publish`.

Combines rcan-py's MlDsaKeyPair with raw Ed25519 bytes (signed wire format
requires both per RCAN 3.0 §2.2). Keys are written to disk under
~/.robot-md/publisher-keys/<github-user>/ on first publish; subsequent
publishes find them.

Layout:
  ~/.robot-md/publisher-keys/<user>/
    ed25519.bin      # 32-byte Ed25519 private (raw)
    ed25519.pub      # 32-byte Ed25519 public (raw)
    ml-dsa.bin       # ML-DSA-65 private (4032 bytes raw)
    ml-dsa.pub       # ML-DSA-65 public (1952 bytes raw)
    metadata.json    # {"pq_kid": "publisher-<user>"}

DO NOT import from rcan.signing — that subpackage is deprecated. Top-level
rcan exports are the public API (rcan.generate_ml_dsa_keypair, rcan.MlDsaKeyPair).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)
from rcan import MlDsaKeyPair, generate_ml_dsa_keypair


@dataclass(frozen=True)
class KeyPair:
    """Combined ML-DSA-65 + Ed25519 keypair for RCAN 3.0 §2.2 signing.

    pq_signing_pub / pq_signing_sec:  ML-DSA-65 public/private bytes (1952 / 4032).
    ed25519_pub / ed25519_sec:        Ed25519 public/private bytes (32 / 32).
    pq_kid:                           Publisher key identifier ("publisher-<user>").
    ml_dsa:                           rcan.MlDsaKeyPair instance for sign_body() calls.
    """

    pq_kid: str
    pq_signing_pub: bytes
    pq_signing_sec: bytes
    ed25519_pub: bytes
    ed25519_sec: bytes
    ml_dsa: MlDsaKeyPair


def publisher_key_dir(user: str) -> Path:
    """Resolve the on-disk directory for a publisher's keypair."""
    if not user:
        raise ValueError("user must be a non-empty string")
    return Path.home() / ".robot-md" / "publisher-keys" / user


def _load_ed25519_raw(priv_path: Path, pub_path: Path) -> tuple[bytes, bytes]:
    return priv_path.read_bytes(), pub_path.read_bytes()


def _generate_ed25519_raw() -> tuple[bytes, bytes]:
    sk = Ed25519PrivateKey.generate()
    sk_raw = sk.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    pk_raw = sk.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return sk_raw, pk_raw


def load_or_mint_publisher_key(user: str) -> KeyPair:
    """Load the publisher's keypair from disk, minting it on first call."""
    if not user:
        raise ValueError("user must be a non-empty string")
    d = publisher_key_dir(user)
    ed_priv = d / "ed25519.bin"
    ed_pub = d / "ed25519.pub"
    pq_priv = d / "ml-dsa.bin"
    pq_pub = d / "ml-dsa.pub"
    meta_path = d / "metadata.json"
    pq_kid = f"publisher-{user}"

    if all(p.is_file() for p in (ed_priv, ed_pub, pq_priv, pq_pub, meta_path)):
        ed_sec, ed_p = _load_ed25519_raw(ed_priv, ed_pub)
        pq_sec = pq_priv.read_bytes()
        pq_p = pq_pub.read_bytes()
        meta = json.loads(meta_path.read_text())
        kp_kid = meta.get("pq_kid", pq_kid)
        ml_dsa_kp = MlDsaKeyPair(key_id=kp_kid, public_key_bytes=pq_p, _secret_key=pq_sec)
        return KeyPair(
            pq_kid=kp_kid,
            pq_signing_pub=pq_p,
            pq_signing_sec=pq_sec,
            ed25519_pub=ed_p,
            ed25519_sec=ed_sec,
            ml_dsa=ml_dsa_kp,
        )

    d.mkdir(parents=True, exist_ok=True)
    ed_sec, ed_p = _generate_ed25519_raw()
    ml_dsa_kp = generate_ml_dsa_keypair()
    pq_p = ml_dsa_kp.public_key_bytes
    pq_sec = ml_dsa_kp._secret_key
    assert pq_sec is not None, "generate_ml_dsa_keypair must return a private half"

    ed_priv.write_bytes(ed_sec)
    ed_pub.write_bytes(ed_p)
    pq_priv.write_bytes(pq_sec)
    pq_pub.write_bytes(pq_p)
    meta_path.write_text(json.dumps({"pq_kid": pq_kid}))

    ml_dsa_kp = MlDsaKeyPair(key_id=pq_kid, public_key_bytes=pq_p, _secret_key=pq_sec)
    return KeyPair(
        pq_kid=pq_kid,
        pq_signing_pub=pq_p,
        pq_signing_sec=pq_sec,
        ed25519_pub=ed_p,
        ed25519_sec=ed_sec,
        ml_dsa=ml_dsa_kp,
    )
