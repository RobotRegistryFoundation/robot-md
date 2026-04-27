from __future__ import annotations

from robot_md.spatial_eval.rrf import submit_evidence


def test_submit_returns_pending_phase_1():
    out = submit_evidence(packet_path="/tmp/evidence", rcan_signature="abc")
    assert out["status"] == "pending_phase_1"
    assert "RRF §27" in out["message"]
