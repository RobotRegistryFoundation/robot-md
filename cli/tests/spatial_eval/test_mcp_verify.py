from __future__ import annotations
from unittest.mock import MagicMock
from robot_md.spatial_eval.score import (
    Aggregate,
    PerUnitExecuteScore,
    ProbeTrack,
    ScoreJSON,
)
from robot_md.mcp.tools.spatial_eval.verify import verify_tool


def _good_score():
    pt = ProbeTrack(baseline_claude={}, robot_declared={}, delta_per_unit={})
    return ScoreJSON(
        spec_version="1.0.0", rrn="RRN-x", run_id="r-1", timestamp="t",
        tracks_probe=pt, tracks_execute={"O1": PerUnitExecuteScore(7, 10, "abc")},
        aggregate=Aggregate(0, 0, 0.7),
        rcan_signature="sig-123", evidence_root="sha256:abc",
    )


def test_verify_accepts_signed_self_attested_score():
    s = _good_score().to_json()
    out = verify_tool(MagicMock(), score_json=s, _verify_signature=lambda payload, sig: True)
    assert out["ok"] is True
    assert out["attestation"] == "self-attested"


def test_verify_rejects_tampered_signature():
    s = _good_score().to_json()
    out = verify_tool(MagicMock(), score_json=s, _verify_signature=lambda payload, sig: False)
    assert out["ok"] is False
    assert "signature" in out["error"]
