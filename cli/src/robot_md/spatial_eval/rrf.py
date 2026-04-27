from __future__ import annotations


def submit_evidence(*, packet_path: str, rcan_signature: str) -> dict:
    """Phase 1 stub. Real submission is wired when RRF §27 endpoints land."""
    return {
        "status": "pending_phase_1",
        "message": (
            "Self-attested evidence is ready. RRF §27 endpoints (counter-signature, "
            "held-out probe re-run, leaderboard) will accept this packet once Phase 1 "
            "ships in a separate plan. Local Score.json is fully usable in the meantime."
        ),
        "packet_path": packet_path,
        "rcan_signature": rcan_signature,
    }
