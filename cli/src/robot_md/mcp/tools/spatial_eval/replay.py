"""MCP tool: spatial_eval_replay — recompute Score JSON from an evidence packet."""

from __future__ import annotations

import datetime as _dt
import json
from collections import defaultdict
from pathlib import Path

from robot_md.spatial_eval.execute.evidence import packet_root_sha256
from robot_md.spatial_eval.score import (
    Aggregate,
    PerUnitExecuteScore,
    ProbeTrack,
    ScoreJSON,
)


def replay_tool(ctx, *, run_dir: Path) -> dict:
    rd = Path(run_dir)
    manifest = json.loads((rd / "manifest.json").read_text())
    counts: dict[str, list[bool]] = defaultdict(list)
    for t in manifest["trials"]:
        counts[t["unit"]].append(bool(t.get("passed")))
    root = packet_root_sha256(rd)
    per_unit = {
        u: PerUnitExecuteScore(passed=sum(rs), n=len(rs), evidence_sha256=root)
        for u, rs in counts.items()
    }
    pt = ProbeTrack(baseline_claude={}, robot_declared={}, delta_per_unit={})
    score = ScoreJSON(
        spec_version="1.0.0",
        rrn="RRN-replayed",
        run_id=rd.name,
        timestamp=_dt.datetime.utcnow().isoformat() + "Z",
        tracks_probe=pt,
        tracks_execute=per_unit,
        aggregate=Aggregate.compute(probe=pt, execute=per_unit),
    )
    return {"ok": True, "score": score.to_dict()}
