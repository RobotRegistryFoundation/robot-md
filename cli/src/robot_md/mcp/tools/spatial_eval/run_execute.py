"""MCP tool: spatial_eval_run_execute — run real-robot trials, write evidence packet."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from robot_md.mcp.tools.spatial_eval._ctx import _frontmatter
from robot_md.spatial_eval.execute.evidence import (
    packet_root_sha256,
    write_evidence_packet,
)
from robot_md.spatial_eval.execute.trial import (
    FakeJudgeCamera,
    FakeRobot,
    run_trial,
)
from robot_md.spatial_eval.score import (
    Aggregate,
    PerUnitExecuteScore,
    ProbeTrack,
    ScoreJSON,
)


def run_execute_tool(
    ctx,
    *,
    units: list[str] | None = None,
    trials_per_unit: int = 10,
    run_dir: Path | None = None,
    _robot=None,
    _judge_camera=None,
) -> dict:
    fm = _frontmatter(ctx)
    se = fm.get("spatial-eval")
    if not se:
        return {"ok": False, "error": "spatial-eval section missing in ROBOT.md"}
    chosen = units or se["units"]
    rd = Path(run_dir or Path("./.spatial_eval_runs") / f"run-{uuid.uuid4().hex[:8]}")
    rd.mkdir(parents=True, exist_ok=True)

    trials_records: list[dict] = []
    per_unit: dict[str, PerUnitExecuteScore] = {}
    for unit in chosen:
        passed = 0
        for t in range(trials_per_unit):
            trial_id = f"{unit.lower()}-trial-{t + 1}"
            try:
                outcome = run_trial(
                    unit=unit,
                    trial_id=trial_id,
                    robot=_robot or FakeRobot(actions=[]),
                    judge_camera=_judge_camera or FakeJudgeCamera(frames=[]),
                    run_dir=rd,
                )
            except Exception as e:
                # Per reviewer T26 note: don't crash the sweep on a single
                # bad frame / judge fault. Emit a structured failure record
                # so downstream Score JSON aggregation still completes.
                outcome = {
                    "trial_id": trial_id,
                    "passed": False,
                    "reason": f"judge_error: {type(e).__name__}: {e}",
                    "unit": unit,
                }
            outcome.setdefault("unit", unit)
            trials_records.append(outcome)
            if outcome.get("passed"):
                passed += 1
        per_unit[unit] = PerUnitExecuteScore(passed=passed, n=trials_per_unit, evidence_sha256="")

    pt = ProbeTrack(baseline_claude={}, robot_declared={}, delta_per_unit={})
    score = ScoreJSON(
        spec_version=se.get("spec_version", "1.0.0"),
        rrn=fm.get("id", "RRN-unknown"),
        run_id=rd.name,
        timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        tracks_probe=pt,
        tracks_execute=per_unit,
        aggregate=Aggregate.compute(probe=pt, execute=per_unit),
    )
    write_evidence_packet(run_dir=rd, trials=trials_records, score=score, videos={})

    # Stamp the deterministic root hash back into per-unit evidence_sha256
    # AFTER the packet is written, then rewrite Score.json with the populated
    # field so downstream verifiers see a self-consistent snapshot.
    root = packet_root_sha256(rd)
    per_unit_with_root = {
        u: PerUnitExecuteScore(passed=v.passed, n=v.n, evidence_sha256=root)
        for u, v in per_unit.items()
    }
    score.tracks_execute = per_unit_with_root
    score.evidence_root = f"sha256:{root}"
    (rd / "Score.json").write_text(score.to_json())
    return {"ok": True, "score": score.to_dict(), "run_dir": str(rd)}
