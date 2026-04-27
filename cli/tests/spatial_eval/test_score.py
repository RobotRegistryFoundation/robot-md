from __future__ import annotations
import json
from robot_md.spatial_eval.score import (
    PerUnitProbeScore, PerUnitExecuteScore, ProbeTrack, ExecuteTrack,
    Aggregate, ScoreJSON,
)

def test_score_json_round_trips():
    s = ScoreJSON(
        spec_version="1.0.0",
        rrn="RRN-000000000002",
        run_id="abc",
        timestamp="2026-04-26T14:30:00Z",
        tracks_probe=ProbeTrack(
            baseline_claude={"O1": PerUnitProbeScore(score=0.87, n=30, passed=26)},
            robot_declared={"O1": PerUnitProbeScore(score=0.84, n=30, passed=25)},
            delta_per_unit={"O1": -0.03},
        ),
        tracks_execute={
            "O1": PerUnitExecuteScore(passed=7, n=10, evidence_sha256="abc..."),
        },
        aggregate=Aggregate(probe_baseline=0.87, probe_declared=0.84, execute=0.7),
        rcan_signature=None,  # added later by signer
        evidence_root=None,
    )
    blob = s.to_json()
    parsed = json.loads(blob)
    assert parsed["spec_version"] == "1.0.0"
    assert parsed["tracks"]["probe"]["delta_per_unit"]["O1"] == -0.03
    s2 = ScoreJSON.from_json(blob)
    assert s2 == s

def test_aggregate_recomputes_from_per_unit():
    pt = ProbeTrack(
        baseline_claude={
            "O1": PerUnitProbeScore(0.8, 30, 24),
            "O2": PerUnitProbeScore(0.6, 30, 18),
        },
        robot_declared={
            "O1": PerUnitProbeScore(0.8, 30, 24),
            "O2": PerUnitProbeScore(0.6, 30, 18),
        },
        delta_per_unit={"O1": 0.0, "O2": 0.0},
    )
    et = {"O1": PerUnitExecuteScore(7, 10, "x")}
    agg = Aggregate.compute(probe=pt, execute=et)
    assert agg.probe_baseline == 0.7  # mean of 0.8, 0.6
    assert agg.execute == 0.7
