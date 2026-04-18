"""MCP tool: execute_task — NL → capability sequence."""

from __future__ import annotations

from typing import Any

from robot_md.mcp.context import McpContext
from robot_md.mcp.tools.execute_capability import execute_capability_tool
from robot_md.planning.decompose import decompose
from robot_md.planning.types import Plan, PlanError


def execute_task_tool(
    ctx: McpContext,
    *,
    prompt: str,
    context: dict[str, Any] | None = None,
    dry_run: bool = False,
    confirm_token: str | None = None,
) -> dict:
    if ctx.backend is None:
        return _error("no_backend", "no backend resolved")
    scene = ctx.backend.scene_describe()
    try:
        plan: Plan = decompose(spec=ctx.spec, scene=scene, user_prompt=prompt)
    except PlanError as e:
        if e.reason in {"low_confidence", "timeout"}:
            return {
                "status": "blocked",
                "plan": [],
                "executions": [],
                "events": [],
                "error": {"reason": e.reason, "detail": e.detail},
            }
        return _error(e.reason, e.detail)

    executions: list[dict] = []
    for step in plan.steps:
        result = execute_capability_tool(
            ctx,
            capability=step.capability,
            args=step.args,
            dry_run=dry_run,
            confirm_token=confirm_token,
        )
        executions.append(result)
        if result["status"] != "ok":
            break

    overall = executions[-1]["status"] if executions else "error"
    return {
        "status": overall,
        "plan": [
            {"capability": s.capability, "args": s.args, "confidence": s.confidence}
            for s in plan.steps
        ],
        "executions": executions,
        "events": [],
    }


def _error(reason: str, message: str) -> dict:
    return {
        "status": "error",
        "plan": [],
        "executions": [],
        "events": [],
        "error": {"reason": reason, "message": message},
    }
