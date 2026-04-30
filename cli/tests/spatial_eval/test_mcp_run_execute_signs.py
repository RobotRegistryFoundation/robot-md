"""SP6 Phase 1 signer wiring: run_execute_tool produces a self-attested
Score JSON when a keypair exists in the keystore for the run's RRN.

End-to-end loop: write keypair → run_execute → re-read on-disk Score.json
→ verify_tool → ok. Tampering or removing the signature breaks
verification (covered by test_mcp_verify_production.py)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np

from robot_md.mcp.tools.spatial_eval.run_execute import run_execute_tool
from robot_md.mcp.tools.spatial_eval.verify import verify_tool
from robot_md.signing import generate_keypair, save_keypair
from robot_md.spatial_eval.execute.trial import FakeJudgeCamera, FakeRobot
from robot_md.spatial_eval.score import ScoreJSON
from robot_md.spatial_eval.sign import try_apikey_sign


def _bgr(c):
    img = np.zeros((240, 320, 3), np.uint8)
    img[:, :] = c
    return img


def _ctx_with_rrn(rrn: str):
    ctx = MagicMock()
    ctx.parsed = {
        "id": rrn,
        "spatial-eval": {
            "spec_version": "1.0.0",
            "units": ["O1"],
            "workspace": {
                "play_surface_dims_m": [0.3, 0.3],
                "judge_camera": {"device": "phone:tripod", "resolution": [1920, 1080]},
            },
            "reasoning_stack": {"baseline": "claude:c", "declared": "claude:c"},
        },
    }
    return ctx


def test_try_apikey_sign_returns_none_when_no_keypair(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    score = ScoreJSON.from_json(
        '{"spec_version":"1.0.0","rrn":"RRN-not-in-store","run_id":"r","timestamp":"t",'
        '"tracks":{"probe":{"baseline_claude":{},"robot_declared":{},"delta_per_unit":{}},'
        '"execute":{}},"aggregate":{"probe_baseline":0,"probe_declared":0,"execute":0},'
        '"rcan_signature":null,"evidence_root":null}'
    )
    assert try_apikey_sign(score) is None


def test_run_execute_signs_score_and_verify_tool_accepts(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    rrn = "RRN-roundtrip"
    save_keypair(rrn, generate_keypair())

    run_dir = tmp_path / "run"
    ctx = _ctx_with_rrn(rrn)
    out = run_execute_tool(
        ctx,
        units=["O1"],
        trials_per_unit=1,
        run_dir=run_dir,
        _robot=FakeRobot(actions=["pick_target_color:red_cube"]),
        _judge_camera=FakeJudgeCamera(frames=[_bgr((0, 0, 255))] * 3),
    )
    assert out["ok"] is True
    on_disk = (run_dir / "Score.json").read_text()
    score = ScoreJSON.from_json(on_disk)
    assert score.rcan_signature is not None and len(score.rcan_signature) > 0
    assert score.rrn == rrn

    verified = verify_tool(MagicMock(), score_json=on_disk)
    assert verified == {"ok": True, "attestation": "self-attested"}


def test_run_execute_leaves_score_unsigned_when_keystore_empty(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    run_dir = tmp_path / "run"
    ctx = _ctx_with_rrn("RRN-no-key")
    out = run_execute_tool(
        ctx,
        units=["O1"],
        trials_per_unit=1,
        run_dir=run_dir,
        _robot=FakeRobot(actions=["pick_target_color:red_cube"]),
        _judge_camera=FakeJudgeCamera(frames=[_bgr((0, 0, 255))] * 3),
    )
    assert out["ok"] is True
    on_disk = (run_dir / "Score.json").read_text()
    score = ScoreJSON.from_json(on_disk)
    assert score.rcan_signature is None
