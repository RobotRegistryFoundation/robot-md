"""MCP tool: spatial_eval_submit_to_rrf — Phase 1.5 RRF §27 submission.

Reads a self-attested Score JSON from `<run_dir>/Score.json`, submits it
to RRF /v1/spatial-eval/runs, returns the parsed response. The signed
score must already exist on disk (produced by `spatial_eval_run_full`
or equivalent); this tool is the upload step, not the sign step.
"""

from __future__ import annotations

from pathlib import Path

from robot_md.spatial_eval.rrf import RrfSubmitError, submit_score
from robot_md.spatial_eval.score import ScoreJSON


def submit_to_rrf_tool(ctx, *, run_dir: str) -> dict:
    score_path = Path(run_dir) / "Score.json"
    if not score_path.exists():
        return {
            "ok": False,
            "error": f"Score.json not found at {score_path}",
        }

    score = ScoreJSON.from_json(score_path.read_text())
    if score.rcan_signature is None:
        return {
            "ok": False,
            "error": (
                f"{score_path} has no rcan_signature — sign the run "
                f"first via spatial_eval_run_execute or spatial_eval_run_full"
            ),
        }

    try:
        result = submit_score(score)
    except RrfSubmitError as e:
        return {"ok": False, "error": str(e)}

    return {"ok": True, **result}
