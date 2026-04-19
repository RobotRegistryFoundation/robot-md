"""MCP tool: estop — set the process-wide estop flag."""

from __future__ import annotations

from robot_md.mcp.context import McpContext


def estop_tool(ctx: McpContext) -> dict:
    ts = ctx.estop.set()
    return {"ok": True, "set_at": ts}


def estop_clear_tool(ctx: McpContext, *, confirm_token: str | None = None) -> dict:
    """Clear the software E-stop. Gated by the `system` HITL scope by default."""
    import time

    spec = ctx.spec
    if spec is not None:
        for gate in spec.safety.hitl_gates:
            if isinstance(gate, dict) and gate.get("scope") == "system":
                if gate.get("require_auth") is not False and not confirm_token:
                    return {
                        "ok": False,
                        "error": {"reason": "hitl_gate", "scope": "system"},
                    }
                break

    ctx.estop.clear()
    return {"ok": True, "cleared_at": time.time()}
