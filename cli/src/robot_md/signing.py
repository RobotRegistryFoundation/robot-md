"""ML-DSA-65 + Ed25519 hybrid signing for robot-md.

Thin wrapper around rcan.crypto (ML-DSA via dilithium-py) and python
cryptography (Ed25519) producing the signed-body shape that RRF's
functions/_lib/verify.ts expects.

Keystore layout: ~/.robot-md/keys/<rrn>.signing.json (mode 600), sibling
of the existing <rrn>.apikey.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric import ed25519
from rcan.crypto import (
    HybridSignature,
    MlDsaKeyPair,
    generate_ml_dsa_keypair,
    sign_hybrid,
    verify_hybrid,
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
    pq_kid: str         # first 8 hex of sha256(ml_dsa.public_key_bytes)


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
    try:
        os.chmod(keystore_dir, KEY_DIR_MODE)
    except OSError:
        pass  # best-effort; filesystem may not support (e.g., Windows)
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


def canonical_json(body: dict[str, Any]) -> bytes:
    """Deterministic JSON — must match TS `JSON.stringify(sortKeys(obj))`."""
    return json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sign_body(kp: SigningKeypair, body: dict[str, Any]) -> dict[str, Any]:
    """Return a COPY of body with pq_signing_pub, pq_kid, sig appended.

    Signs over canonical_json({**body, pq_signing_pub, pq_kid}) — the IDs
    are PART of the signed message, matching RRF's register.ts and PATCH
    [rrn]/index.ts wire formats. verify_body strips only `sig` before
    re-canonicalizing, which recovers the same signed message.
    """
    pq_pub_b64 = base64.b64encode(kp.ml_dsa.public_key_bytes).decode()
    body_with_ids = {**body, "pq_signing_pub": pq_pub_b64, "pq_kid": kp.pq_kid}
    message = canonical_json(body_with_ids)
    hs = sign_hybrid(kp.ml_dsa, kp.ed25519_sec, message)
    return {
        **body_with_ids,
        "sig": {
            "ml_dsa": base64.b64encode(hs.ml_dsa_sig).decode(),
            "ed25519": base64.b64encode(hs.ed25519_sig).decode(),
            "ed25519_pub": base64.b64encode(kp.ed25519_pub).decode(),
        },
    }


def verify_body(signed: dict[str, Any]) -> bool:
    """Strip `sig`, canonicalize the rest (INCLUDING pq_signing_pub + pq_kid),
    hybrid-verify. Matches RRF's wire format for register + PATCH.
    """
    try:
        sig = signed.get("sig")
        if not sig:
            return False
        pq_pub_b64 = signed.get("pq_signing_pub")
        if not pq_pub_b64:
            return False
        rest = {k: v for k, v in signed.items() if k != "sig"}
        message = canonical_json(rest)
        verify_hybrid(
            ml_dsa_public_key_bytes=base64.b64decode(pq_pub_b64),
            ed25519_public_key_bytes=base64.b64decode(sig["ed25519_pub"]),
            message=message,
            hybrid_sig=HybridSignature(
                ml_dsa_sig=base64.b64decode(sig["ml_dsa"]),
                ed25519_sig=base64.b64decode(sig["ed25519"]),
                kid=signed.get("pq_kid", ""),
            ),
        )
        return True
    except Exception:
        return False
