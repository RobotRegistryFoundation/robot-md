"""MCP tool: spatial_eval_run_full — chain probe + execute and merge tracks."""

from __future__ import annotations

from pathlib import Path

from robot_md.mcp.tools.spatial_eval.run_execute import run_execute_tool
from robot_md.mcp.tools.spatial_eval.run_probe import run_probe_tool


def run_full_tool(
    ctx,
    *,
    units: list[str] | None = None,
    trials_per_unit: int = 10,
    run_dir: Path | None = None,
    _stacks=None,
    _robot=None,
    _judge_camera=None,
) -> dict:
    p = run_probe_tool(ctx, units=units, _stacks=_stacks)
    if not p["ok"]:
        return p
    e = run_execute_tool(
        ctx,
        units=units,
        trials_per_unit=trials_per_unit,
        run_dir=run_dir,
        _robot=_robot,
        _judge_camera=_judge_camera,
    )
    if not e["ok"]:
        return e
    merged = e["score"]
    merged["tracks"]["probe"] = p["score"]["tracks"]["probe"]
    merged["aggregate"]["probe_baseline"] = p["score"]["aggregate"]["probe_baseline"]
    merged["aggregate"]["probe_declared"] = p["score"]["aggregate"]["probe_declared"]
    return {"ok": True, "score": merged, "run_dir": e["run_dir"]}
