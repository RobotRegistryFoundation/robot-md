"""MCP tool: spatial_eval_dry_run — pre-flight checks before a run."""

from __future__ import annotations

import os

from robot_md.mcp.tools.spatial_eval._ctx import _frontmatter


def dry_run_tool(ctx) -> dict:
    se = _frontmatter(ctx).get("spatial-eval")
    checks: dict[str, str] = {}
    checks["spatial_eval_section"] = "present" if se else "missing"
    checks["anthropic_api_key"] = "set" if os.environ.get("ANTHROPIC_API_KEY") else "missing"
    if se:
        wc = se.get("workspace", {}).get("judge_camera", {}).get("device")
        checks["judge_camera_device"] = wc or "missing"
    ok = all(v not in ("missing", None) for v in checks.values())
    return {"ok": ok, "checks": checks}
