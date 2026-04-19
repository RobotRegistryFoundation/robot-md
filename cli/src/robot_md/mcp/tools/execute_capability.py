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

    # Safety short-circuits come first — E-stop is a hard stop that should
    # outrank any consent workflow. A HITL gate satisfied between estop-set
    # and command-dispatch must not race past a stopped server.
    read_only = getattr(ctx.backend, "read_only_capabilities", frozenset())
    if ctx.estop.is_set() and capability not in read_only:
        return {"status": "blocked", "trajectory": None, "events": [],
                "error": {"reason": "estop_set"}}

    gate = _match_hitl_gate(ctx, capability)
    if gate and not _gate_satisfied(gate, confirm_token):
        return {
            "status": "blocked",
            "trajectory": None,
            "events": [],
            "error": {"reason": "hitl_gate", "scope": gate.get("scope")},
        }

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
    """Gate check — v0.3 uses opaque stub tokens.

    Any truthy token value satisfies `require_auth: true`. Tokens are NOT
    cryptographically verified, NOT single-use, and NOT bound to a gate
    scope. A caller can legitimately re-use the same string for every
    step of a multi-step `execute_task`. Signed/bound tokens are a v0.4+
    feature (tracked in the v0.3.0 spec "Out of scope" list).

    If you need authority in your deployment today, enforce it at the
    MCP-client tier (whatever proxies tool calls to this server).
    """
    if gate.get("require_auth") is False:
        return True
    return bool(token)
