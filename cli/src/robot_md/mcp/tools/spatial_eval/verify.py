"""MCP tool: spatial_eval_verify — verify a self-attested Score JSON signature."""

from __future__ import annotations

from collections.abc import Callable

from robot_md.spatial_eval.score import ScoreJSON


def verify_tool(
    ctx,
    *,
    score_json: str,
    _verify_signature: Callable[[bytes, str], bool] | None = None,
) -> dict:
    score = ScoreJSON.from_json(score_json)
    if score.rcan_signature is None:
        return {"ok": False, "error": "no rcan_signature on Score JSON"}
    payload = score.to_json().encode("utf-8")
    if _verify_signature is None:
        # Per reviewer T28/T29 note: signers are dependency-injected. The
        # production wiring lands in a later task; until then, callers must
        # inject a verifier explicitly.
        return {"ok": False, "error": "production verifier not wired"}
    if not _verify_signature(payload, score.rcan_signature):
        return {"ok": False, "error": "invalid signature"}
    return {"ok": True, "attestation": "self-attested"}
