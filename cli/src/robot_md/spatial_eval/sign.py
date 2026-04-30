"""Self-attested signing helpers for Score JSON.

Pairs with cli/src/robot_md/mcp/tools/spatial_eval/verify.py — the
canonicalization (rcan_signature=None at sign-and-verify time) is the
same in both directions.
"""

from __future__ import annotations

import base64
import json

from robot_md.spatial_eval.score import ScoreJSON


def payload_bytes(score: ScoreJSON) -> bytes:
    """Canonical bytes for ML-DSA signing/verification.

    Both `rcan_signature` and `rrf_signature` are cleared. The robot's
    self-attestation is computed first (rrf_signature is None at that
    time), and RRF's counter-signature is computed against the same
    canonical bytes (so RRF endorses exactly what the robot signed). At
    verify time both are cleared so a registry-attested score still
    self-verifies.
    """
    d = score.to_dict()
    d["rcan_signature"] = None
    d["rrf_signature"] = None
    return json.dumps(d, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_score(score: ScoreJSON, kp) -> str:
    """Sign `score` with the SigningKeypair `kp`. Returns base64 sig."""
    from rcan.crypto import sign_ml_dsa

    sig_bytes = sign_ml_dsa(kp.ml_dsa, payload_bytes(score))
    return base64.b64encode(sig_bytes).decode("ascii")


def try_apikey_sign(score: ScoreJSON) -> str | None:
    """Look up the keystore keypair for `score.rrn`, sign the score, return
    the base64 sig string. Returns None when no keypair is on disk —
    production callers leave the score unsigned in that case so downstream
    `spatial_eval_verify` returns the standard "no rcan_signature on
    Score JSON" error rather than crashing.
    """
    from robot_md.signing import load_keypair

    kp = load_keypair(score.rrn)
    if kp is None:
        return None
    return sign_score(score, kp)
