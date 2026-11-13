"""MCP tool: execute_task — NL → capability plan, each step sent to robot-md-gateway.

The planner proposes a sequence of declared capabilities. Each step goes
through `execute_capability`, which sends it to the gateway; nothing here
touches the robot. The first step that does not come back `ok` (`dry_run` on
a dry run) ends the task, so nothing is sent after a refusal.
"""

from __future__ import annotations

from typing import Any

from robot_md import gateway_client
from robot_md.backends.base import SceneSnapshot
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
) -> dict:
    # Refuse before planning: a plan nothing can execute is a wasted planner
    # call, and a refusal later would look like a planning problem.
    config = gateway_client.config_for_context(ctx)
    if not config.ready:
        return _error(
            "gateway_not_configured",
            "motion goes through robot-md-gateway, and none is configured: "
            + " ".join(config.problems),
        )

    scene = SceneSnapshot.empty()
    if ctx.backend is not None:
        try:
            scene = ctx.backend.scene_describe()
        except Exception:
            scene = SceneSnapshot.empty()
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

    proceed = "dry_run" if dry_run else "ok"
    executions: list[dict] = []
    for step in plan.steps:
        result = execute_capability_tool(
            ctx,
            capability=step.capability,
            args=step.args,
            dry_run=dry_run,
        )
        executions.append(result)
        if result["status"] != proceed:
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
