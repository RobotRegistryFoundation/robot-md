"""SP6 Phase 1.5 — verify_tool extended with rrf_signature recognition.

When both signatures are present and both verify, the tool returns
`attestation: registry-attested`. When the rrf_signature is present
but no RRF-pubkey verifier is wired, the tool returns self-attested
with a warning (Phase 1.5 production reality: RRF spec endpoint
serving the pubkey doesn't exist yet).
"""

from __future__ import annotations

from unittest.mock import MagicMock

from robot_md.mcp.tools.spatial_eval.verify import verify_tool
from robot_md.spatial_eval.score import (
    Aggregate,
    PerUnitExecuteScore,
    ProbeTrack,
    ScoreJSON,
)


def _score_with(rcan: str | None, rrf: str | None) -> str:
    s = ScoreJSON(
        spec_version="1.0.0",
        rrn="RRN-x",
        run_id="r-1",
        timestamp="t",
        tracks_probe=ProbeTrack(baseline_claude={}, robot_declared={}, delta_per_unit={}),
        tracks_execute={"O1": PerUnitExecuteScore(7, 10, "abc")},
        aggregate=Aggregate(0, 0, 0.7),
        rcan_signature=rcan,
        rrf_signature=rrf,
        evidence_root="sha256:abc",
    )
    return s.to_json()


def test_verify_score_with_both_sigs_returns_registry_attested():
    out = verify_tool(
        MagicMock(),
        score_json=_score_with("rcan-sig", "rrf-sig"),
        _verify_signature=lambda payload, sig: True,
        _verify_rrf_signature=lambda payload, sig: True,
    )
    assert out == {"ok": True, "attestation": "registry-attested"}


def test_verify_rejects_invalid_rrf_signature():
    out = verify_tool(
        MagicMock(),
        score_json=_score_with("rcan-sig", "rrf-sig"),
        _verify_signature=lambda payload, sig: True,
        _verify_rrf_signature=lambda payload, sig: False,
    )
    assert out["ok"] is False
    assert "invalid rrf_signature" in out["error"]


def test_verify_score_with_rrf_sig_but_no_rrf_verifier_falls_back_to_self_attested_with_warning():
    """Phase 1.5 production path: rrf_signature is present on the score but
    RRF's public key isn't fetchable yet (spec endpoint not built). Don't
    claim registry-attested without verifying — return self-attested with
    a clear warning so callers see the situation."""
    out = verify_tool(
        MagicMock(),
        score_json=_score_with("rcan-sig", "rrf-sig"),
        _verify_signature=lambda payload, sig: True,
        # _verify_rrf_signature=None  -- omitted on purpose
    )
    assert out["ok"] is True
    assert out["attestation"] == "self-attested"
    assert "rrf_signature present" in out["warning"]


def test_verify_score_without_rrf_sig_still_returns_self_attested():
    """Regression: existing self-attested behavior unchanged when rrf_signature is None."""
    out = verify_tool(
        MagicMock(),
        score_json=_score_with("rcan-sig", None),
        _verify_signature=lambda payload, sig: True,
    )
    assert out == {"ok": True, "attestation": "self-attested"}


def test_verify_invalid_rcan_short_circuits_before_rrf_check():
    """An invalid rcan_signature must fail BEFORE the rrf_signature path,
    even when an rrf-verifier would have accepted. The robot's self-sig
    is the foundation — without it, registry endorsement is meaningless."""
    out = verify_tool(
        MagicMock(),
        score_json=_score_with("rcan-sig", "rrf-sig"),
        _verify_signature=lambda payload, sig: False,
        _verify_rrf_signature=lambda payload, sig: True,
    )
    assert out["ok"] is False
    assert out["error"] == "invalid signature"
