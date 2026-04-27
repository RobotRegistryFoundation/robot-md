"""ML-DSA-65 + Ed25519 hybrid signing for robot-md.

Thin wrapper around rcan.crypto (ML-DSA via dilithium-py) and python
cryptography (Ed25519) producing the signed-body shape that RRF's
functions/_lib/verify.ts expects.

Keystore layout: ~/.robot-md/keys/<rrn>.signing.json (mode 600), sibling
of the existing <rrn>.apikey.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric import ed25519
from rcan import canonical_json as _rcan_canonical_json
from rcan import sign_body as _rcan_sign_body
from rcan import verify_body as _rcan_verify_body
from rcan.crypto import (
    MlDsaKeyPair,
    generate_ml_dsa_keypair,
)

KEYSTORE_DIR = Path.home() / ".robot-md" / "keys"
KEY_FILE_MODE = 0o600
KEY_DIR_MODE = 0o700


@dataclass
class SigningKeypair:
    """ML-DSA-65 + Ed25519 keypair bundle for a single robot."""

    ml_dsa: MlDsaKeyPair
    ed25519_pub: bytes  # 32 bytes raw
    ed25519_sec: bytes  # 32 bytes raw
    pq_kid: str  # first 8 hex of sha256(ml_dsa.public_key_bytes)


def kid_from_pub(ml_dsa_pub: bytes) -> str:
    return hashlib.sha256(ml_dsa_pub).hexdigest()[:8]


def generate_keypair() -> SigningKeypair:
    ml_kp = generate_ml_dsa_keypair()
    ed_sec = ed25519.Ed25519PrivateKey.generate()
    return SigningKeypair(
        ml_dsa=ml_kp,
        ed25519_pub=ed_sec.public_key().public_bytes_raw(),
        ed25519_sec=ed_sec.private_bytes_raw(),
        pq_kid=kid_from_pub(ml_kp.public_key_bytes),
    )


def _keypath(rrn: str) -> Path:
    return Path.home() / ".robot-md" / "keys" / f"{rrn}.signing.json"


def save_keypair(rrn: str, kp: SigningKeypair) -> Path:
    keystore_dir = Path.home() / ".robot-md" / "keys"
    keystore_dir.mkdir(parents=True, exist_ok=True)
    with suppress(OSError):
        os.chmod(keystore_dir, KEY_DIR_MODE)
    path = _keypath(rrn)
    data = {
        "rrn": rrn,
        "pq_kid": kp.pq_kid,
        "ml_dsa": {
            "pub": base64.b64encode(kp.ml_dsa.public_key_bytes).decode(),
            "sec": base64.b64encode(kp.ml_dsa._secret_key).decode(),
        },
        "ed25519": {
            "pub": base64.b64encode(kp.ed25519_pub).decode(),
            "sec": base64.b64encode(kp.ed25519_sec).decode(),
        },
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    # Write to tmp then rename to avoid partial writes; set mode 600 before content
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.chmod(tmp, KEY_FILE_MODE)
    tmp.replace(path)
    return path


def load_keypair(rrn: str) -> SigningKeypair | None:
    path = _keypath(rrn)
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    ml_pub = base64.b64decode(data["ml_dsa"]["pub"])
    ml_sec = base64.b64decode(data["ml_dsa"]["sec"])
    return SigningKeypair(
        ml_dsa=MlDsaKeyPair(
            key_id=data["pq_kid"],
            public_key_bytes=ml_pub,
            _secret_key=ml_sec,
        ),
        ed25519_pub=base64.b64decode(data["ed25519"]["pub"]),
        ed25519_sec=base64.b64decode(data["ed25519"]["sec"]),
        pq_kid=data["pq_kid"],
    )


# ----------------------------------------------------------------------
# v1.0.1 — dict-level signing now lives in rcan.hybrid + rcan.encoding.
# These thin adapters preserve robot-md's ergonomic SigningKeypair
# wrapper (one arg, unpacked to rcan's keyword form) so existing callers
# in register.py, benchmarks.py, etc. don't change.
# ----------------------------------------------------------------------


def canonical_json(body: dict[str, Any]) -> bytes:
    """Deterministic JSON — delegates to rcan.encoding.canonical_json."""
    return _rcan_canonical_json(body)


def sign_body(kp: SigningKeypair, body: dict[str, Any]) -> dict[str, Any]:
    """Unpack SigningKeypair and call rcan.hybrid.sign_body.

    Wire format unchanged: body + pq_signing_pub + pq_kid + sig.
    """
    return _rcan_sign_body(
        kp.ml_dsa,
        body,
        ed25519_secret=kp.ed25519_sec,
        ed25519_public=kp.ed25519_pub,
    )


def verify_body(signed: dict[str, Any]) -> bool:
    """Delegates to rcan.hybrid.verify_body with pq_signing_pub pulled from payload."""
    pq_pub_b64 = signed.get("pq_signing_pub")
    if not pq_pub_b64:
        return False
    try:
        pq_pub = base64.b64decode(pq_pub_b64)
    except (ValueError, binascii.Error):
        return False
    return _rcan_verify_body(signed, pq_pub)


def _verify_with_pq_pub(signed: dict[str, Any], pq_pub_b64: str) -> bool:
    """Verify a signed dict where the public key is *not* at top-level ``pq_signing_pub``.

    Used for the FriaDocument nested-key shape, where the public key lives under
    ``signing_key.public_key`` rather than top-level ``pq_signing_pub``.

    Re-injects ``pq_signing_pub`` from the supplied argument before delegating
    to ``_rcan_verify_body`` so the canonicalized pre-image matches what
    ``sign_body`` produced.

    Returns False on any decode/verify error (mirrors verify_body).
    """
    try:
        pq_pub = base64.b64decode(pq_pub_b64)
    except (ValueError, binascii.Error):
        return False
    signed_with_pub = {**signed, "pq_signing_pub": pq_pub_b64}
    return _rcan_verify_body(signed_with_pub, pq_pub)
