"""MCP tool: spatial_eval_run_full — chain probe + execute and merge tracks."""

from __future__ import annotations

import json
from pathlib import Path

from robot_md.mcp.tools.spatial_eval.run_execute import run_execute_tool
from robot_md.mcp.tools.spatial_eval.run_probe import run_probe_tool
from robot_md.spatial_eval.score import ScoreJSON
from robot_md.spatial_eval.sign import try_apikey_sign


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

    # The on-disk Score.json was signed by run_execute_tool over the
    # execute-only canonical bytes. Merging probe data invalidated that
    # signature; clear it, re-sign over the merged bytes, and re-write
    # the on-disk file so what's returned matches what's persisted (and
    # verifies cleanly).
    merged["rcan_signature"] = None
    merged_score = ScoreJSON.from_json(json.dumps(merged, sort_keys=True))
    sig = try_apikey_sign(merged_score)
    if sig is not None:
        merged_score.rcan_signature = sig
        merged["rcan_signature"] = sig

    (Path(e["run_dir"]) / "Score.json").write_text(merged_score.to_json())
    return {"ok": True, "score": merged, "run_dir": e["run_dir"]}
