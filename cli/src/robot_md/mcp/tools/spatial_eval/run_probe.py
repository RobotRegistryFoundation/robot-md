"""MCP tool: spatial_eval_run_probe — answer probe set with baseline +/- declared stack."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from robot_md.mcp.tools.spatial_eval._ctx import _frontmatter
from robot_md.spatial_eval.probe.datasets.loader import load_public_split
from robot_md.spatial_eval.probe.runner import run_probes
from robot_md.spatial_eval.probe.stacks import resolve_stack
from robot_md.spatial_eval.score import (
    Aggregate,
    ProbeTrack,
    ScoreJSON,
)


def run_probe_tool(
    ctx,
    *,
    units: list[str] | None = None,
    baseline_only: bool = False,
    _stacks: dict | None = None,
) -> dict:
    fm = _frontmatter(ctx)
    se = fm.get("spatial-eval")
    if not se:
        return {"ok": False, "error": "spatial-eval section missing in ROBOT.md"}
    chosen = units or se["units"]
    by_unit = load_public_split()
    probes = [p for u in chosen for p in by_unit.get(u, [])]
    if not probes:
        return {"ok": False, "error": f"no probes for units {chosen}"}

    if _stacks is not None:
        baseline = _stacks["baseline"]
        declared = _stacks["declared"]
    else:
        baseline = resolve_stack(se["reasoning_stack"]["baseline"])
        declared = baseline if baseline_only else resolve_stack(se["reasoning_stack"]["declared"])

    try:
        result = run_probes(
            probes,
            baseline=baseline,
            declared=None if baseline_only else declared,
        )
    except Exception as e:
        return {"ok": False, "error": f"probe_runner_error: {type(e).__name__}: {e}"}

    # Per reviewer T25 note: in baseline_only mode, leave declared track and
    # delta empty (NOT a copy of baseline) so consumers can distinguish a
    # single-stack run from "two stacks agreed".
    pt = ProbeTrack(
        baseline_claude=result.baseline_per_unit,
        robot_declared={} if baseline_only else result.declared_per_unit,
        delta_per_unit={} if baseline_only else result.delta_per_unit,
    )
    score = ScoreJSON(
        spec_version=se.get("spec_version", "1.0.0"),
        rrn=fm.get("id", "RRN-unknown"),
        run_id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        tracks_probe=pt,
        tracks_execute={},
        aggregate=Aggregate.compute(probe=pt, execute={}),
    )
    return {"ok": True, "score": score.to_dict(), "per_probe": result.per_probe}
