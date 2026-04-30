"""MCP tool: spatial_eval_verify — verify a self-attested Score JSON signature.

Phase 1: production verifier wired. By default, verify_tool loads the
ML-DSA signing keypair from ~/.robot-md/keys/<rrn>.signing.json (the
same keystore that holds the apikey-signed RRF artifacts) and verifies
the Score JSON's `rcan_signature` against the canonical bytes of the
score with `rcan_signature` cleared (you can't sign over your own
signature).

Tests inject `_verify_signature` to skip the keystore lookup; production
callers leave it None.
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Callable

from robot_md.spatial_eval.score import ScoreJSON
from robot_md.spatial_eval.sign import payload_bytes


def _make_apikey_verifier(rrn: str) -> Callable[[bytes, str], bool] | None:
    """Build a (payload, sig_b64) -> bool verifier bound to the keystore
    keypair for `rrn`. Returns None if the keystore has no entry — callers
    should surface that as a clean error.
    """
    from rcan.crypto import verify_ml_dsa

    from robot_md.signing import load_keypair

    kp = load_keypair(rrn)
    if kp is None:
        return None

    pq_pub = kp.ml_dsa.public_key_bytes

    def verify(payload: bytes, sig_b64: str) -> bool:
        try:
            sig_bytes = base64.b64decode(sig_b64)
        except (ValueError, binascii.Error):
            return False
        try:
            verify_ml_dsa(pq_pub, payload, sig_bytes)
        except Exception:
            return False
        return True

    return verify


def verify_tool(
    ctx,
    *,
    score_json: str,
    _verify_signature: Callable[[bytes, str], bool] | None = None,
) -> dict:
    score = ScoreJSON.from_json(score_json)
    if score.rcan_signature is None:
        return {"ok": False, "error": "no rcan_signature on Score JSON"}

    payload = payload_bytes(score)

    if _verify_signature is None:
        _verify_signature = _make_apikey_verifier(score.rrn)
        if _verify_signature is None:
            return {
                "ok": False,
                "error": (
                    f"no signing keypair for {score.rrn} in keystore — "
                    f"register the robot or restore ~/.robot-md/keys/{score.rrn}.signing.json"
                ),
            }

    if not _verify_signature(payload, score.rcan_signature):
        return {"ok": False, "error": "invalid signature"}

    return {"ok": True, "attestation": "self-attested"}
