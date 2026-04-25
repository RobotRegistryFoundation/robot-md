"""MCP tool: estop — set the process-wide estop flag."""

from __future__ import annotations

import contextlib

from robot_md.mcp.context import McpContext


def _audit_estop(ctx: McpContext, event: str, details: dict) -> None:
    """Append a tamper-evident entry for an e-stop set/clear.

    Setting and clearing the software e-stop is THE canonical reactive-
    safety action — agents/operators trip it in response to environmental
    cues. Recording every set/clear (and every denied clear) gives an
    EU AI Act notified body the Article 9 + Article 12 evidence chain.
    No-op on unregistered manifests; audit failures must never crash the
    e-stop call itself.
    """
    rrn = None
    spec = getattr(ctx, "spec", None)
    if spec is not None:
        meta = getattr(spec, "metadata", None)
        if meta is not None:
            rrn = getattr(meta, "rrn", None)
    if not rrn:
        return
    from robot_md.audit import record_event

    # Audit failures must never crash an e-stop call.
    with contextlib.suppress(Exception):
        record_event(rrn, event=event, details={"tool": "estop", **details})


def estop_tool(ctx: McpContext) -> dict:
    ts = ctx.estop.set()
    _audit_estop(ctx, event="estop_set", details={"set_at": ts})
    if getattr(ctx, "publisher", None) is not None:
        ctx.publisher.publish("estop.set", {"set": True})
    return {"ok": True, "set_at": ts}


def estop_clear_tool(ctx: McpContext, *, confirm_token: str | None = None) -> dict:
    """Clear the software E-stop. Gated by the `system` HITL scope by default."""
    import time

    spec = ctx.spec
    if spec is not None:
        for gate in spec.safety.hitl_gates:
            if isinstance(gate, dict) and gate.get("scope") == "system":
                if gate.get("require_auth") is not False and not confirm_token:
                    _audit_estop(
                        ctx,
                        event="estop_clear_denied",
                        details={"reason": "hitl_gate", "scope": "system"},
                    )
                    return {
                        "ok": False,
                        "error": {"reason": "hitl_gate", "scope": "system"},
                    }
                break

    ctx.estop.clear()
    cleared_at = time.time()
    _audit_estop(ctx, event="estop_cleared", details={"cleared_at": cleared_at})
    if getattr(ctx, "publisher", None) is not None:
        ctx.publisher.publish("estop.cleared", {"set": False})
    return {"ok": True, "cleared_at": cleared_at}
