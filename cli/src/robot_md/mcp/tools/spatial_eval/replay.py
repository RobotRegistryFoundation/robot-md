"""MCP tool: spatial_eval_replay — recompute Score JSON from an evidence packet."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
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

    # Preserve provenance from the original Score.json when present.
    spec_version = "1.0.0"
    rrn = "RRN-replayed"
    score_path = rd / "Score.json"
    if score_path.exists():
        try:
            prior = json.loads(score_path.read_text())
            if isinstance(prior, dict):
                if isinstance(prior.get("spec_version"), str):
                    spec_version = prior["spec_version"]
                if isinstance(prior.get("rrn"), str):
                    rrn = prior["rrn"]
        except json.JSONDecodeError:
            pass

    score = ScoreJSON(
        spec_version=spec_version,
        rrn=rrn,
        run_id=rd.name,
        timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        tracks_probe=pt,
        tracks_execute=per_unit,
        aggregate=Aggregate.compute(probe=pt, execute=per_unit),
    )
    return {"ok": True, "score": score.to_dict()}
