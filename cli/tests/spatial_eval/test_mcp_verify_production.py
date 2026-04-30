"""SP6 Phase 1: production apikey-verifier wiring.

Without an injected `_verify_signature`, verify_tool now loads the
keystore keypair for the Score JSON's RRN and verifies via
rcan.crypto.verify_ml_dsa over the canonical payload (with
rcan_signature cleared, so we don't sign over our own signature).
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from rcan.crypto import sign_ml_dsa

from robot_md.mcp.tools.spatial_eval.verify import verify_tool
from robot_md.signing import generate_keypair, save_keypair
from robot_md.spatial_eval.score import (
    Aggregate,
    PerUnitExecuteScore,
    ProbeTrack,
    ScoreJSON,
)


def _score_with_rrn(rrn: str) -> ScoreJSON:
    pt = ProbeTrack(baseline_claude={}, robot_declared={}, delta_per_unit={})
    return ScoreJSON(
        spec_version="1.0.0",
        rrn=rrn,
        run_id="r-1",
        timestamp="2026-04-30T07:00:00Z",
        tracks_probe=pt,
        tracks_execute={"O1": PerUnitExecuteScore(7, 10, "abc")},
        aggregate=Aggregate(0.0, 0.0, 0.7),
        rcan_signature=None,
        evidence_root="sha256:abc",
    )


def _payload_for_signing(score: ScoreJSON) -> bytes:
    """Match the verify_tool's canonicalization: rcan_signature must be None
    when computing the bytes that get signed/verified."""
    d = score.to_dict()
    d["rcan_signature"] = None
    return json.dumps(d, sort_keys=True, separators=(",", ":")).encode("utf-8")


def test_production_verifier_accepts_well_signed_score(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    kp = generate_keypair()
    rrn = "RRN-test-001"
    save_keypair(rrn, kp)

    score = _score_with_rrn(rrn)
    payload = _payload_for_signing(score)
    sig = base64.b64encode(sign_ml_dsa(kp.ml_dsa, payload)).decode("ascii")
    score.rcan_signature = sig

    out = verify_tool(MagicMock(), score_json=score.to_json())
    assert out == {"ok": True, "attestation": "self-attested"}


def test_production_verifier_rejects_tampered_signature(
    monkeypatch, tmp_path: Path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    kp = generate_keypair()
    rrn = "RRN-test-002"
    save_keypair(rrn, kp)

    score = _score_with_rrn(rrn)
    payload = _payload_for_signing(score)
    sig_bytes = sign_ml_dsa(kp.ml_dsa, payload)
    tampered = bytearray(sig_bytes)
    tampered[5] ^= 0x01
    score.rcan_signature = base64.b64encode(bytes(tampered)).decode("ascii")

    out = verify_tool(MagicMock(), score_json=score.to_json())
    assert out["ok"] is False
    assert "signature" in out["error"]


def test_production_verifier_rejects_tampered_payload(
    monkeypatch, tmp_path: Path,
) -> None:
    """Sign one score; then mutate a non-signature field and ask the verifier
    to check it. The signature was over the pre-mutation canonical bytes,
    so verification must fail."""
    monkeypatch.setenv("HOME", str(tmp_path))
    kp = generate_keypair()
    rrn = "RRN-test-003"
    save_keypair(rrn, kp)

    score = _score_with_rrn(rrn)
    payload = _payload_for_signing(score)
    score.rcan_signature = base64.b64encode(sign_ml_dsa(kp.ml_dsa, payload)).decode("ascii")

    score.run_id = "tampered-run-id"

    out = verify_tool(MagicMock(), score_json=score.to_json())
    assert out["ok"] is False
    assert "signature" in out["error"]


def test_production_verifier_keystore_miss_returns_clean_error(
    monkeypatch, tmp_path: Path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    score = _score_with_rrn("RRN-no-key-here")
    score.rcan_signature = base64.b64encode(b"any-bytes-here-the-key-is-missing").decode("ascii")

    out = verify_tool(MagicMock(), score_json=score.to_json())
    assert out["ok"] is False
    assert "keystore" in out["error"] or "no signing keypair" in out["error"]


def test_production_verifier_returns_no_signature_error_when_unsigned(
    monkeypatch, tmp_path: Path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    score = _score_with_rrn("RRN-unsigned")
    out = verify_tool(MagicMock(), score_json=score.to_json())
    assert out == {"ok": False, "error": "no rcan_signature on Score JSON"}
