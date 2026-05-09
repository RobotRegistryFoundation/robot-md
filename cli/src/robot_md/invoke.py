"""robot-md invoke — production RCAN INVOKE envelope sender.

Builds a signed RCAN INVOKE envelope and POSTs it to a robot-md-gateway
`/v1/invoke` endpoint. Operators use this for real dispatches; cookbook
readers use it as the actuation step in beat 6.

No mocks. No demo flags. The signing path uses the operator's
`~/.robot-md/keys/<rrn>.signing.json` keypair (same convention as
`robot-md register`).
"""

from __future__ import annotations

import base64
import secrets
import time
import uuid
from typing import Any

from cryptography.hazmat.primitives.asymmetric import ed25519
from rcan.audit_bundle import canonical_json

from robot_md.signing import SigningKeypair


def build_envelope(
    *,
    ruri: str,
    tool_name: str,
    tool_args: dict[str, Any],
    manifest_path: str,
    scope: str = "actuate",
) -> dict[str, Any]:
    """Construct a fresh RCAN INVOKE envelope.

    Returned dict shape matches `robot_md_gateway.receiver.InvokeEnvelope`
    plus `nonce` + `timestamp_ms` for replay protection.
    """
    return {
        "msg_id": str(uuid.uuid4()),
        "type": "rcan/v1/invoke",
        "ruri": ruri,
        "scope": scope,
        "tool_name": tool_name,
        "tool_args": tool_args,
        "manifest_path": manifest_path,
        "nonce": secrets.token_hex(16),
        "timestamp_ms": int(time.time() * 1000),
    }


def sign_envelope(
    envelope: dict[str, Any],
    keypair: SigningKeypair,
    *,
    kid: str,
) -> dict[str, Any]:
    """Sign an envelope with Ed25519 and return a copy with envelope_signature attached.

    Signature is over `canonical_json(signed_envelope, exclude="envelope_signature")`
    matching the gateway's `verify_envelope` pre-image (cert/envelope.py:57).

    Args:
        envelope: dict from build_envelope (or compatible)
        keypair: operator's signing keypair (from ~/.robot-md/keys/<rrn>.signing.json)
        kid: key id to advertise in the envelope; gateway resolves to a
             registered Ed25519 public key via RRFResolver.

    Returns: a new dict (input is not mutated) with `envelope_signature` set.
    """
    out = dict(envelope)
    out["envelope_signature"] = {"kid": kid, "sig": ""}  # placeholder for canon
    pre = canonical_json(out, exclude="envelope_signature")
    sec = ed25519.Ed25519PrivateKey.from_private_bytes(keypair.ed25519_sec)
    sig = sec.sign(pre)
    out["envelope_signature"] = {"kid": kid, "sig": base64.b64encode(sig).decode()}
    return out
