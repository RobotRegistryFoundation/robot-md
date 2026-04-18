"""MCP tool: execute_capability — deterministic primitive."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from robot_md.mcp.context import McpContext


def execute_capability_tool(
    ctx: McpContext,
    *,
    capability: str,
    args: dict[str, Any],
    dry_run: bool,
    confirm_token: str | None,
) -> dict:
    if ctx.backend is None:
        return _error("no_backend", "no backend resolved for any driver")
    declared = ctx.spec.capabilities if ctx.spec is not None else frozenset()
    if capability not in declared:
        return _error("not_declared", f"capability '{capability}' not in spec.capabilities")
    if capability not in ctx.backend.capabilities():
        return _error("not_implemented", f"backend does not implement '{capability}'")

    gate = _match_hitl_gate(ctx, capability)
    if gate and not _gate_satisfied(gate, confirm_token):
        return {
            "status": "blocked",
            "trajectory": None,
            "events": [],
            "error": {"reason": "hitl_gate", "scope": gate.get("scope")},
        }

    if ctx.estop.is_set():
        return {"status": "blocked", "trajectory": None, "events": [],
                "error": {"reason": "estop_set"}}

    if not ctx.exec_lock.acquire(blocking=False):
        return {"status": "blocked", "trajectory": None, "events": [],
                "error": {"reason": "busy"}}
    try:
        result = ctx.backend.execute(
            capability=capability, args=args, dry_run=dry_run, estop=ctx.estop
        )
        return {
            "status": result.status,
            "trajectory": result.trajectory,
            "events": [asdict(e) for e in result.events],
            "error": result.error,
        }
    finally:
        ctx.exec_lock.release()


def _error(reason: str, message: str) -> dict:
    return {
        "status": "error",
        "trajectory": None,
        "events": [],
        "error": {"reason": reason, "message": message},
    }


def _match_hitl_gate(ctx: McpContext, capability: str) -> dict | None:
    spec = ctx.spec
    if spec is None:
        return None
    cap_scope = capability.split(".", 1)[0]
    for gate in spec.safety.hitl_gates:
        scope = gate.get("scope") if isinstance(gate, dict) else None
        if scope == cap_scope or scope == capability:
            return gate if isinstance(gate, dict) else None
    return None


def _gate_satisfied(gate: dict, token: str | None) -> bool:
    if gate.get("require_auth") is False:
        return True
    return bool(token)
