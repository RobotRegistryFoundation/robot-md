"""MCP tool: execute_capability — deterministic primitive."""

from __future__ import annotations

import time
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
    # Generate request_id and publish tool.call before any early-exit so
    # EVERY invocation — even no_backend failures — reaches the InvocationLog
    # and events.jsonl. Observability must see the call the operator made.
    request_id = f"{capability}-{int(time.time() * 1000)}"
    if getattr(ctx, "publisher", None) is not None:
        ctx.publisher.publish(
            "tool.call",
            {
                "tool": "execute_capability",
                "capability": capability,
                "args": args,
                "dry_run": dry_run,
                "request_id": request_id,
            },
        )

    if ctx.backend is None:
        result = _error("no_backend", "no backend resolved for any driver")
        _publish_result(ctx, request_id, capability, result)
        return result

    declared = ctx.spec.capabilities if ctx.spec is not None else frozenset()
    if capability not in declared:
        result = _error("not_declared", f"capability '{capability}' not in spec.capabilities")
        _publish_result(ctx, request_id, capability, result)
        return result
    if capability not in ctx.backend.capabilities():
        result = _error("not_implemented", f"backend does not implement '{capability}'")
        _publish_result(ctx, request_id, capability, result)
        return result

    # Safety short-circuits come first — E-stop is a hard stop that should
    # outrank any consent workflow. A HITL gate satisfied between estop-set
    # and command-dispatch must not race past a stopped server.
    read_only = getattr(ctx.backend, "read_only_capabilities", frozenset())
    if ctx.estop.is_set() and capability not in read_only:
        result = {
            "status": "blocked",
            "trajectory": None,
            "events": [],
            "error": {"reason": "estop_set"},
        }
        _publish_result(ctx, request_id, capability, result)
        return result

    # Precondition gate — consult capability_contracts[capability].preconditions.
    # Estop above already ran and returned for non-read-only caps. Read-only
    # caps bypass preconditions for the same reason they bypass estop:
    # observability must survive calibration gaps.
    if capability not in read_only:
        contract = ctx.spec.capability_contracts.get(capability) if ctx.spec else None
        if contract is not None and contract.preconditions:
            from dataclasses import asdict as _asdict

            from robot_md.preconditions import evaluate

            ok, failures = evaluate(contract, ctx.spec, backend_resolved=ctx.backend is not None)
            if not ok:
                result = {
                    "status": "blocked",
                    "trajectory": None,
                    "events": [],
                    "error": {
                        "reason": "precondition",
                        "preconditions": [_asdict(f) for f in failures],
                    },
                }
                _publish_result(ctx, request_id, capability, result)
                return result

    gate = _match_hitl_gate(ctx, capability)
    if gate and not _gate_satisfied(gate, confirm_token):
        result = {
            "status": "blocked",
            "trajectory": None,
            "events": [],
            "error": {"reason": "hitl_gate", "scope": gate.get("scope")},
        }
        _publish_result(ctx, request_id, capability, result)
        return result

    if not ctx.exec_lock.acquire(blocking=False):
        result = {
            "status": "blocked",
            "trajectory": None,
            "events": [],
            "error": {"reason": "busy"},
        }
        _publish_result(ctx, request_id, capability, result)
        return result
    try:
        exec_result = ctx.backend.execute(
            capability=capability, args=args, dry_run=dry_run, estop=ctx.estop
        )
        result = {
            "status": exec_result.status,
            "trajectory": exec_result.trajectory,
            "events": [asdict(e) for e in exec_result.events],
            "error": exec_result.error,
        }
        _publish_result(ctx, request_id, capability, result)
        return result
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
        if scope in (cap_scope, capability):
            return gate if isinstance(gate, dict) else None
    return None


def _publish_result(ctx: McpContext, request_id: str, capability: str, result: dict) -> None:
    if getattr(ctx, "publisher", None) is None:
        return
    ctx.publisher.publish(
        "tool.result",
        {
            "tool": "execute_capability",
            "capability": capability,
            "status": result.get("status"),
            "request_id": request_id,
            "error": result.get("error"),
        },
    )


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
