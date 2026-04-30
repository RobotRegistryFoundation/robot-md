"""SP6 Phase 1.5+ — verify_tool production wiring for the RRF counter-signature.

When `_verify_rrf_signature` is not injected and the score has an
rrf_signature, verify_tool now fetches the RRF pubkey from
GET /v1/spatial-eval/spec/{spec_version} and verifies. Network failures
fall back to self-attested with a warning rather than failing the score.
"""

from __future__ import annotations

import base64
import io
import json
import urllib.error
from pathlib import Path
from unittest.mock import patch

from rcan.crypto import sign_ml_dsa

from robot_md.mcp.tools.spatial_eval.verify import verify_tool
from robot_md.signing import generate_keypair, save_keypair
from robot_md.spatial_eval.score import (
    Aggregate,
    PerUnitExecuteScore,
    ProbeTrack,
    ScoreJSON,
)
from robot_md.spatial_eval.sign import payload_bytes


def _mock_response(status: int, body: dict | bytes = b"") -> object:
    class _Resp:
        def __init__(self):
            self.status = status
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            self._fp = io.BytesIO(data)

        def read(self):
            return self._fp.read()

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    return _Resp()


def _registry_attested_score(monkeypatch, tmp_path: Path):
    """Build a Score JSON with both rcan_signature (real, against a robot
    keypair saved to keystore) and rrf_signature (real, against a
    test RRF keypair). Returns (score_json_str, rrf_keypair) where
    rrf_keypair is whatever generate_keypair() produces."""
    monkeypatch.setenv("HOME", str(tmp_path))

    rrn = "RRN-test-rrf-001"
    robot_kp = generate_keypair()
    save_keypair(rrn, robot_kp)

    score = ScoreJSON(
        spec_version="1.0.0",
        rrn=rrn,
        run_id="r-1",
        timestamp="2026-04-30T00:00:00Z",
        tracks_probe=ProbeTrack(baseline_claude={}, robot_declared={}, delta_per_unit={}),
        tracks_execute={"O1": PerUnitExecuteScore(7, 10, "abc")},
        aggregate=Aggregate(0.0, 0.0, 0.7),
        rcan_signature=None,
        rrf_signature=None,
        evidence_root="sha256:abc",
    )
    payload = payload_bytes(score)
    score.rcan_signature = base64.b64encode(sign_ml_dsa(robot_kp.ml_dsa, payload)).decode("ascii")

    # Test RRF keypair
    rrf_kp = generate_keypair()
    score.rrf_signature = base64.b64encode(sign_ml_dsa(rrf_kp.ml_dsa, payload)).decode("ascii")

    return score.to_json(), rrf_kp


def test_verify_returns_registry_attested_when_spec_endpoint_serves_pubkey(
    monkeypatch, tmp_path: Path
):
    score_json, rrf_kp = _registry_attested_score(monkeypatch, tmp_path)
    rrf_pubkey_b64 = base64.b64encode(rrf_kp.ml_dsa.public_key_bytes).decode("ascii")

    def fake_urlopen(req, timeout=None):
        return _mock_response(
            200,
            {
                "spec_version": "1.0.0",
                "rrf_pubkey": rrf_pubkey_b64,
                "rrf_pubkey_alg": "ml-dsa-65",
            },
        )

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        out = verify_tool(None, score_json=score_json)

    assert out == {"ok": True, "attestation": "registry-attested"}


def test_verify_falls_back_to_self_attested_when_spec_endpoint_unreachable(
    monkeypatch, tmp_path: Path
):
    score_json, _rrf_kp = _registry_attested_score(monkeypatch, tmp_path)

    def fake_urlopen(req, timeout=None):
        raise urllib.error.URLError("Network unreachable")

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        out = verify_tool(None, score_json=score_json)

    assert out["ok"] is True
    assert out["attestation"] == "self-attested"
    assert "RRF public key could not be fetched" in out["warning"]


def test_verify_falls_back_to_self_attested_when_spec_endpoint_404(monkeypatch, tmp_path: Path):
    score_json, _rrf_kp = _registry_attested_score(monkeypatch, tmp_path)

    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", hdrs={}, fp=io.BytesIO(b"{}"))

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        out = verify_tool(None, score_json=score_json)

    assert out["ok"] is True
    assert out["attestation"] == "self-attested"
    assert "RRF public key could not be fetched" in out["warning"]


def test_verify_rejects_when_pubkey_returned_but_rrf_sig_invalid(monkeypatch, tmp_path: Path):
    """RRF endpoint returns a (different) pubkey that doesn't match the
    rrf_signature on the score. Must be a hard fail, not a soft fallback —
    a serving-but-wrong pubkey is more concerning than an unreachable one."""
    score_json, _rrf_kp = _registry_attested_score(monkeypatch, tmp_path)

    # Use a completely different RRF keypair for the fetched pubkey
    other_rrf = generate_keypair()
    bad_pubkey_b64 = base64.b64encode(other_rrf.ml_dsa.public_key_bytes).decode("ascii")

    def fake_urlopen(req, timeout=None):
        return _mock_response(200, {"rrf_pubkey": bad_pubkey_b64})

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        out = verify_tool(None, score_json=score_json)

    assert out["ok"] is False
    assert "invalid rrf_signature" in out["error"]


def test_verify_uses_custom_rrf_endpoint(monkeypatch, tmp_path: Path):
    score_json, rrf_kp = _registry_attested_score(monkeypatch, tmp_path)
    rrf_pubkey_b64 = base64.b64encode(rrf_kp.ml_dsa.public_key_bytes).decode("ascii")

    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        return _mock_response(200, {"rrf_pubkey": rrf_pubkey_b64})

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        verify_tool(None, score_json=score_json, rrf_endpoint="http://localhost:8765")

    assert captured["url"].startswith("http://localhost:8765")
