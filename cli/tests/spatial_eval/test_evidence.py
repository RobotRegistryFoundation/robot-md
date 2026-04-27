from __future__ import annotations

from pathlib import Path

from robot_md.spatial_eval.execute.evidence import (
    packet_root_sha256,
    write_evidence_packet,
)
from robot_md.spatial_eval.score import (
    Aggregate,
    PerUnitExecuteScore,
    ProbeTrack,
    ScoreJSON,
)


def _stub_score() -> ScoreJSON:
    pt = ProbeTrack(baseline_claude={}, robot_declared={}, delta_per_unit={})
    return ScoreJSON(
        spec_version="1.0.0",
        rrn="RRN-x",
        run_id="r-1",
        timestamp="t",
        tracks_probe=pt,
        tracks_execute={"O1": PerUnitExecuteScore(7, 10, "ev")},
        aggregate=Aggregate(0, 0, 0.7),
    )


def test_packet_writes_files_and_hash_is_deterministic(tmp_path: Path):
    trials = [{"trial_id": "t1", "passed": True, "reason": "ok"}]
    write_evidence_packet(
        run_dir=tmp_path,
        trials=trials,
        score=_stub_score(),
        videos={"t1": b"\x00\x01"},
    )
    assert (tmp_path / "manifest.json").is_file()
    assert (tmp_path / "Score.json").is_file()
    assert (tmp_path / "videos/t1.mp4").is_file()
    h1 = packet_root_sha256(tmp_path)
    h2 = packet_root_sha256(tmp_path)
    assert h1 == h2
    assert len(h1) == 64
